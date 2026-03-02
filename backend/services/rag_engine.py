"""RAG engine for retrieval and answer generation."""
from typing import List, Dict, Tuple, Any
from services.vector_store import vector_store, jira_vector_store
from services.bedrock_client import bedrock_client
from services.memory_service import memory_service
from services.retriever import get_retriever, CrossEncoderRetriever
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG retrieval and generation engine."""
    
    def retrieve(self, query: str, top_k: int = None, use_reranking: bool = None) -> Tuple[str, List[str], Any]:
        """
        Retrieve relevant context for a query from both JIRA and PDF collections.
        
        Args:
            query: User query
            top_k: Number of results to retrieve per collection
            
        Returns:
            Tuple of (formatted_context, source_list)
        """
        if top_k is None:
            top_k = max(settings.top_k_results, 15)

        # Pre-retrieval metadata filtering (JIRA-specific)
        filter_dict = None
        try:
            from services.jira.query_metadata_extractor import extract_query_metadata
            extracted = extract_query_metadata(query)
            if extracted:
                filter_dict = extracted
                logger.info(f"Applying pre-retrieval metadata filter: {filter_dict}")
        except Exception as e:
            logger.debug(f"Metadata extraction skipped: {e}")

        # ── JIRA retrieval (Hybrid: Dense jira_vector_store + BM25 OpenSearch → RRF → CrossEncoder) ──
        jira_results = None
        rerank_summary = None
        try:
            from services.bm25_store import bm25_store
            from services.hybrid_retriever import HybridRetriever
            if bm25_store.is_ready():
                logger.info(f"Using HybridRetriever (BM25={bm25_store.count()} tickets) + CrossEncoder on jira_vector_store")
                _hybrid = HybridRetriever(jira_vector_store, bm25_store)
                retriever = CrossEncoderRetriever(jira_vector_store)
                retriever._hybrid = _hybrid
                fused = _hybrid.retrieve(query, top_k=top_k, filter_dict=filter_dict)
                jira_results = retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict,
                                                  precomputed_candidates=fused)
                rerank_summary = jira_results.get('rerank_summary')
            else:
                logger.info("BM25 index empty — using dense-only on jira_vector_store")
                retriever = get_retriever(settings, jira_vector_store, use_reranking=use_reranking)
                jira_results = retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict)
        except Exception as e:
            logger.debug(f"JIRA retrieval error, falling back to jira_vector_store dense: {e}")
            try:
                retriever = get_retriever(settings, jira_vector_store, use_reranking=use_reranking)
                jira_results = retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict)
            except Exception:
                jira_results = None

        # ── PDF / document retrieval (Dense vector_store only) ──────────────────
        pdf_results = None
        try:
            pdf_retriever = get_retriever(settings, vector_store, use_reranking=False)
            pdf_results = pdf_retriever.retrieve(query, top_k=top_k)
            if pdf_results and pdf_results.get('documents'):
                logger.info("PDF collection returned results")
        except Exception as e:
            logger.debug(f"PDF retrieval error: {e}")

        # ── Merge both result sets ────────────────────────────────────────────────
        def _safe_docs(res):
            if not res or not res.get('documents'):
                return [], []
            docs = res['documents']
            metas = res['metadatas']
            if docs and isinstance(docs[0], list):
                docs = docs[0]
                metas = metas[0] if metas else []
            return docs, metas

        jdocs, jmetas = _safe_docs(jira_results)
        pdocs, pmetas = _safe_docs(pdf_results)

        all_docs = jdocs + pdocs
        all_metas = jmetas + pmetas

        if not all_docs:
            logger.warning("No relevant documents found in either collection")
            return "", [], None

        # Pack back into results dict for the rest of the function
        results = {'documents': all_docs, 'metadatas': all_metas}


        # Format context from retrieved chunks
        context_parts = []
        sources = []
        
        # Handle ChromaDB structure which is sometimes nested
        docs = results['documents']
        metas = results['metadatas']
        
        # Access nested list if it exists and is not empty
        if docs and isinstance(docs[0], list):
            docs = docs[0]
            metas = metas[0] if metas else []

        if not docs:
            logger.warning("No relevant documents found after unpacking")
            return "", [], None

        # --- Date-aware sorting ---
        # If the query contains date/ordering language, sort chunks chronologically
        # so Claude receives them in the correct order and can present accurate lists.
        _SORT_SIGNALS = {"ascending", "descending", "recent", "latest", "oldest", 
                         "order", "date", "created", "chronological", "last 10", "first", "sorted"}
        query_lower = query.lower()
        should_sort = any(sig in query_lower for sig in _SORT_SIGNALS)
        
        if should_sort and metas:
            from email.utils import parsedate_to_datetime
            _LARGE_TS = float('inf')  # undated tickets go to the END
            
            def _parse_date(meta):
                created = meta.get("created", "")
                try:
                    return parsedate_to_datetime(created).timestamp() if created else _LARGE_TS
                except Exception:
                    return _LARGE_TS
            
            # Zip together and sort ascending by default
            paired = sorted(zip(docs, metas), key=lambda x: _parse_date(x[1]))
            # Reverse for descending/recent if requested
            if "descending" in query_lower or ("recent" in query_lower and "ascending" not in query_lower):
                paired = list(reversed(paired))
            docs = [p[0] for p in paired]
            metas = [p[1] for p in paired]
            logger.info(f"Sorted {len(docs)} chunks by created date ({'asc' if 'ascending' in query_lower else 'desc/recent'})")

        for i, (doc, metadata) in enumerate(zip(docs, metas), 1):
            # JIRA tickets: use ticket_id as source. PDFs: use filename + page.
            ticket_id = metadata.get('ticket_id', '')
            vector_type = metadata.get('vector_type', '')
            created = metadata.get('created', '')
            status = metadata.get('status', '')

            if ticket_id:
                source_label = f"{ticket_id}"
                if vector_type:
                    source_label += f" [{vector_type}]"
                if created:
                    source_label += f" | Created: {created}"
                if status:
                    source_label += f" | Status: {status}"
                source_ref = ticket_id
            else:
                filename = metadata.get('filename', 'Unknown')
                page = metadata.get('page', 'N/A')
                source_label = f"{filename}, Page {page}"
                source_ref = f"{filename} (Page {page})"

            context_parts.append(f"[Source {i}: {source_label}]\n{doc}\n")
            if source_ref not in sources:
                sources.append(source_ref)
        
        logger.info(f"Retrieved {len(sources)} unique sources")
        
        formatted_context = "\n".join(context_parts)
        
        logger.info(f"Retrieved {len(results['documents'])} chunks from {len(sources)} sources")
        logger.debug(f"Retrieved Context Preview: {formatted_context[:500]}...")
        
        return formatted_context, sources, results.get('rerank_summary')

    
    def generate_answer(
        self,
        query: str,
        context: str,
        session_id: str,
        conversation_history: List[Dict[str, str]] = None,
        use_knowledge_base: bool = True
    ) -> str:
        """
        Generate an answer using RAG and semantic memory.
        
        Args:
            query: User query
            context: Retrieved context
            session_id: current session ID
            conversation_history: Previous messages (last 5)
            use_knowledge_base: Whether knowledge base is enabled
            
        Returns:
            Generated answer
        """
        # Retrieve semantic memories for this session
        memories = memory_service.get_memories(session_id, query=query)
        memory_str = ""
        if memories:
            memory_list = []
            for m in memories:
                if isinstance(m, dict) and 'rules' in m:
                    memory_list.extend(m['rules'])
                else:
                    memory_list.append(str(m))
            memory_str = "Session Context/Rules:\n- " + "\n- ".join(memory_list)
            logger.info(f"Retrieved semantic memory for session {session_id}")
        
        # Combine context with semantic memory if present
        full_context = context
        if memory_str:
            full_context = f"{memory_str}\n\nDocument Context:\n{context}" if context else memory_str

        # Generate response using Bedrock
        response = bedrock_client.generate_response(
            user_message=query,
            context=full_context,
            conversation_history=conversation_history,
            use_knowledge_base=use_knowledge_base
        )
        
        return response
    
    def _contextualize_query(self, query: str, conversation_history: List[Dict[str, str]]) -> str:
        """
        Expand a follow-up question with context from conversation history
        to prevent context drift during retrieval.

        If the user says "give me dates again" or "tell me more about that",
        we don't want to query the vector store with those words — we want to
        query it with the original topic (e.g., "VIA supervisor issues").

        Detection: if the current query is short AND contains follow-up signals,
        we prepend the last user message to anchor the retrieval.
        """
        _FOLLOWUP_SIGNALS = {
            "again", "more", "full", "whole", "same",
            "above", "those", "that", "them", "repeat", "previous", "earlier", "all of",
            "list them", "show me", "tell me", "give me", "what about", "any more",
            "continue", "summarize", "summary"
        }
        query_lower = query.lower().strip()
        is_short = len(query.split()) <= 12
        has_signal = any(sig in query_lower for sig in _FOLLOWUP_SIGNALS)
        # Self-contained check: if the query has a capitalized ticket/system keyword or year, it's standalone
        import re
        has_topic = bool(re.search(r'\b(HCLSM-\d+|\d{4}|PDA|VIA|WEXLOG|COES|FIELDEAS|CONTINENTAL|SUPERVISOR|JASPER|ZEBRA|CEE)\b', query, re.IGNORECASE))

        # Don't contextualize if the query is self-contained (has topic anchor)
        if is_short and has_signal and not has_topic and conversation_history:
            # Find the last user message (it holds the original topic)
            last_user_query = None
            for msg in reversed(conversation_history):
                if msg.get("role") == "user":
                    last_user_query = msg.get("content", "").strip()
                    break

            if last_user_query and last_user_query.lower() != query_lower:
                expanded = f"{last_user_query} {query}"
                logger.info(f"ContextualizedQuery: '{query}' → '{expanded[:120]}'")
                return expanded

        return query

    def chat(
        self,
        query: str,
        session_id: str,
        conversation_history: List[Dict[str, str]] = None,
        use_knowledge_base: bool = True,
        use_reranking: bool = None
    ) -> Tuple[str, List[str], Any]:
        """
        Complete RAG chat: retrieve context and generate answer.
        
        Args:
            query: User query
            session_id: Current session ID
            conversation_history: Previous messages
            use_knowledge_base: Whether to use the vector knowledge base
            
        Returns:
            Tuple of (answer, sources, rerank_summary)
        """
        # Step 1: Build a retrieval query anchored to the conversation topic
        retrieval_query = query
        if use_knowledge_base and conversation_history:
            retrieval_query = self._contextualize_query(query, conversation_history)

        # Step 2: Retrieve relevant context (only if enabled)
        context = ""
        sources = []
        rerank_summary = None
        if use_knowledge_base:
            context, sources, rerank_summary = self.retrieve(retrieval_query, use_reranking=use_reranking)
        
        # Step 3: Generate answer (always uses the original query so Claude answers naturally)
        answer = self.generate_answer(query, context, session_id, conversation_history, use_knowledge_base)
        
        return answer, sources, rerank_summary


# Global RAG engine instance
rag_engine = RAGEngine()

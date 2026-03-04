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
    
    def _compute_top_k(self, query: str, base_top_k: int) -> int:
        """
        Dynamically increase top_k for exhaustive listing queries.
        When users say "list all", "give me all", "minimum N" etc. we need to
        cast a wide net so the same set of docs appears on every attempt,
        eliminating the inconsistency caused by random chunk sampling.
        """
        import re
        LIST_SIGNALS = re.compile(
            r'\ball\b|\bevery\b|\blist\b|\benumerate\b|\bfull list\b'
            r'|\bminimum\s+\d+\b|\bat\s+least\s+\d+\b'
            r'|\b\d{2,}\s+report|report\s+names?\b'
            r'|how many|complete list|give me all|find all|show all',
            re.IGNORECASE
        )
        if LIST_SIGNALS.search(query):
            boosted = min(base_top_k * 4, 60)  # 4× boost, hard cap 60
            logger.info(f"Listing query detected — boosting top_k {base_top_k} → {boosted}")
            return boosted
        return base_top_k

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
        top_k = self._compute_top_k(query, top_k)

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
            return "", [], None, []

        # ── Date-aware sorting ─────────────────────────────────────────────────
        docs, metas = all_docs, all_metas
        _SORT_SIGNALS = {"ascending", "descending", "recent", "latest", "oldest",
                         "order", "date", "created", "chronological", "last 10", "first", "sorted"}
        query_lower = query.lower()
        if any(sig in query_lower for sig in _SORT_SIGNALS) and metas:
            from email.utils import parsedate_to_datetime
            _LARGE_TS = float('inf')

            def _parse_date(meta):
                created = meta.get("created", "")
                try:
                    return parsedate_to_datetime(created).timestamp() if created else _LARGE_TS
                except Exception:
                    return _LARGE_TS

            paired = sorted(zip(docs, metas), key=lambda x: _parse_date(x[1]))
            if "descending" in query_lower or ("recent" in query_lower and "ascending" not in query_lower):
                paired = list(reversed(paired))
            docs  = [p[0] for p in paired]
            metas = [p[1] for p in paired]
            logger.info(f"Sorted {len(docs)} chunks by date")

        # ── Build context string + consolidated citations ──────────────────────────
        context_parts = []
        sources = []
        citations_map = {} # Map source_id -> citation dict
        source_ref_to_index = {} # Map source_id to 1-based index (for S1, S2...)
        
        # We index unique sources as S1, S2...
        # This ensures the LLM cites the source, not the chunk index.
        for i, (doc, metadata) in enumerate(zip(docs, metas), 1):
            ticket_id = metadata.get('ticket_id', '')
            created = metadata.get('created', '')
            status = metadata.get('status', '')

            if ticket_id:
                source_ref = ticket_id
                source_type = "jira"
                source_label = ticket_id
            else:
                filename = metadata.get('filename', 'Unknown')
                source_ref = filename
                source_type = "pdf"
                source_label = filename

            # Assign unique source index
            if source_ref not in source_ref_to_index:
                source_ref_to_index[source_ref] = len(source_ref_to_index) + 1
                sources.append(source_ref)
            
            s_idx = source_ref_to_index[source_ref]

            # Sequential numbering [Source S1: label] for LLM context
            context_parts.append(f"[Source S{s_idx}: {source_label}]\n{doc}\n")

            if source_ref not in citations_map:
                citations_map[source_ref] = {
                    "id":          source_ref,
                    "label":       source_label,
                    "snippet":     doc[:600].strip(),
                    "source_type": source_type,
                    "metadata":    {
                        "ticket_id": ticket_id,
                        "created":   created,
                        "status":    status,
                        "priority":  metadata.get('priority', ''),
                        "filename":  metadata.get('filename', ''),
                        "pages":     [metadata.get('page')] if metadata.get('page') else [],
                        "count":     1,
                        "source_index": s_idx
                    },
                }
            else:
                cite = citations_map[source_ref]
                # Merge snippets if they are from the same source
                if len(cite["snippet"]) < 1200:
                    cite["snippet"] += f"\n\n... [Cont'd (S{s_idx})] ...\n\n{doc[:400].strip()}"
                
                cite["metadata"]["count"] += 1
                page = metadata.get('page')
                if page and page not in cite["metadata"]["pages"]:
                    cite["metadata"]["pages"].append(page)

        # Convert map to list and sort by source index
        # We remove the hard limit of 20 to ensure all sources mentioned in response can be found
        citations = sorted(list(citations_map.values()), key=lambda x: x["metadata"]["source_index"])

        logger.info(f"Retrieved {len(docs)} chunks, consolidated into {len(citations)} source cards")
        formatted_context = "\n".join(context_parts)
        return formatted_context, sources, rerank_summary, citations

    
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
        response, gen_metrics = bedrock_client.generate_response(
            user_message=query,
            context=full_context,
            conversation_history=conversation_history,
            use_knowledge_base=use_knowledge_base
        )

        return response, gen_metrics
    
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

    def _is_casual_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> bool:
        """
        Detect whether a query is casual/conversational and does NOT need RAG retrieval.

        Returns True  → skip knowledge base, answer directly.
        Returns False → perform full RAG retrieval.

        Strategy:
          1. Hard-pass IT signals: ticket IDs, error/bug/issue/fix keywords,
             system names, ordering signals → always retrieve.
          2. Casual patterns: greetings, who/what is the agent, small talk → skip.
          3. Short queries with no IT domain signal → skip.
        """
        q = query.strip().lower()

        # ── 1. Hard IT-domain signals → always retrieve ───────────────────────
        import re
        IT_SIGNALS_RE = re.compile(
            r'\bHCLSM-\d+\b'                     # ticket ID
            r'|\bticket\b|\bissue\b|\bbug\b|\berror\b|\bcrash\b'
            r'|\bfix\b|\bresolve\b|\bresolution\b|\bproblem\b'
            r'|\bincident\b|\boutage\b|\bfailure\b'
            r'|\bwexlog\b|\bcoes\b|\bfieldeas\b|\bjasper\b|\bzebra\b'
            r'|\bpda\b|\bvia\b|\bsupervisor\b|\bcee\b|\bsap\b|\berp\b'
            r'|\bserver\b|\bdatabase\b|\bdeploy\b|\bscript\b'
            r'|\bdocument\b|\breport\b|\blogs?\b'
            r'|\blast\s+\d+\b|\btop\s+\d+\b'
            r'|\brecent\b|\blatest\b|\boldest\b'
            r'|\bascending\b|\bdescending\b'
            r'|\bclosed\b|\bassigned\b|\bpriority\b|\bstatus\b'
            r'|\bhow\s+(was|were|is|are)\b'
            r'|\bwhy\s+(is|was|are|were|did)\b'
            r'|\bwhat\s+happened\b|\bwent\s+wrong\b'
            r'|tell me (about|more about|details|all).*(ticket|issue|error|pda|via|hclsm)',
            re.IGNORECASE
        )
        if IT_SIGNALS_RE.search(query):
            logger.debug(f"IT signal detected — will retrieve: '{query[:80]}'")
            return False

        # ── 2. Definite casual patterns → skip retrieval ─────────────────────
        CASUAL_PATTERNS = [
            # Greetings
            r'^(hi|hello|hey|howdy|good\s?(morning|afternoon|evening|day|night))[!.,?\s]*$',
            r'^(how are you|how do you do|what\'?s up|sup|yo)[!.,?\s]*$',
            # Identity / creator questions
            r'^(who are you|what are you|introduce yourself|tell me about yourself|your name)[?!.,\s]*$',
            r'(who (made|built|created|developed) you)',
            r'(are you (from|by|made by|created by|built by))',
            r'(not\s+(anthropic|openai|google|amazon|perplex|claude|ai))',
            r'(perplex.*(squad|team)|squad.*(team|perplex))',
            r'(you.*created by|created by.*you)',
            # Acknowledgements / reactions
            r'^(thanks?|thank you|thx|ty|cheers|appreciate it?)[!.,?\s]*$',
            r'^(ok|okay|got it|understood|sure|alright|great|nice|cool|awesome|perfect|wow)[!.,?\s]*$',
            r'^(no|nope|nah|yes|yeah|yep|correct|exactly|right|wrong|really)[!.,?\s]*$',
            r'^(not really|of course|absolutely|definitely)[!.,?\s]*$',
            r'^(bye|goodbye|see you|cya|later|good night)[!.,?\s]*$',
            # Meta
            r'^what (can|do) you (do|help|assist)[?!.,\s]*$',
            r'^help( me)?[?!.,\s]*$',
        ]
        for pattern in CASUAL_PATTERNS:
            if re.search(pattern, q, re.IGNORECASE):
                logger.debug(f"Casual pattern match — skipping retrieval: '{query[:80]}'")
                return True

        # ── 3. Short query with no IT signal → skip ───────────────────────────
        word_count = len(query.split())
        if word_count <= 8:
            logger.debug(f"Short non-IT query ({word_count}w) — skipping retrieval: '{query[:80]}'")
            return True

        # Default: retrieve for anything longer / ambiguous
        return False

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
        import time
        t0 = time.time()

        # Step 1: Detect casual intent — skip RAG for conversational queries
        if use_knowledge_base and self._is_casual_query(query, conversation_history):
            logger.info(f"Casual query detected — bypassing retrieval: '{query[:80]}'")
            answer, gen_m = self.generate_answer(query, "", session_id, conversation_history, use_knowledge_base=False)
            metrics = {
                "latency_s":       round(time.time() - t0, 3),
                "retrieval_s":     0.0,
                "generation_s":    gen_m.get("generation_s", 0.0),
                "input_tokens":    gen_m.get("input_tokens", 0),
                "output_tokens":   gen_m.get("output_tokens", 0),
                "total_tokens":    gen_m.get("total_tokens", 0),
                "query_type":      "casual",
                "sources_retrieved": 0,
            }
            return answer, [], None, metrics, []

        # Step 2: Build a retrieval query anchored to the conversation topic
        retrieval_query = query
        if use_knowledge_base and conversation_history:
            retrieval_query = self._contextualize_query(query, conversation_history)

        # Step 3: Retrieve context + citations (only if KB enabled)
        context = ""
        sources = []
        rerank_summary = None
        citations = []
        retrieval_s = 0.0
        if use_knowledge_base:
            t_ret = time.time()
            context, sources, rerank_summary, citations = self.retrieve(retrieval_query, use_reranking=use_reranking)
            retrieval_s = round(time.time() - t_ret, 3)

        # Step 4: Generate answer
        answer, gen_m = self.generate_answer(query, context, session_id, conversation_history, use_knowledge_base)

        metrics = {
            "latency_s":       round(time.time() - t0, 3),
            "retrieval_s":     retrieval_s,
            "generation_s":    gen_m.get("generation_s", 0.0),
            "input_tokens":    gen_m.get("input_tokens", 0),
            "output_tokens":   gen_m.get("output_tokens", 0),
            "total_tokens":    gen_m.get("total_tokens", 0),
            "query_type":      "rag",
            "sources_retrieved": len(sources),
        }
        return answer, sources, rerank_summary, metrics, citations


# Global RAG engine instance
rag_engine = RAGEngine()

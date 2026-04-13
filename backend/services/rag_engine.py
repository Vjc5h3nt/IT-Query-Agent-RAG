"""RAG engine for retrieval and answer generation."""
import re
import time
import logging
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Tuple

from app.config import settings
from services.bedrock_client import bedrock_client
from services.memory_service import memory_service
from services.retriever import CrossEncoderRetriever, get_retriever
from services.vector_store import jira_vector_store, vector_store

logger = logging.getLogger(__name__)

# ── Module-level compiled regex patterns ──────────────────────────────────────

_LIST_SIGNALS_RE = re.compile(
    r'\ball\b|\bevery\b|\blist\b|\benumerate\b|\bfull list\b'
    r'|\bminimum\s+\d+\b|\bat\s+least\s+\d+\b'
    r'|\b\d{2,}\s+report|report\s+names?\b'
    r'|how many|complete list|give me all|find all|show all',
    re.IGNORECASE
)

_IT_SIGNALS_RE = re.compile(
    r'\bHCLSM-\d+\b'
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

_CASUAL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'^(hi|hello|hey|howdy|good\s?(morning|afternoon|evening|day|night))[!.,?\s]*$',
        r'^(how are you|how do you do|what\'?s up|sup|yo)[!.,?\s]*$',
        r'^(who are you|what are you|introduce yourself|tell me about yourself|your name)[?!.,\s]*$',
        r'(who (made|built|created|developed) you)',
        r'(are you (from|by|made by|created by|built by))',
        r'(not\s+(anthropic|openai|google|amazon|perplex|claude|ai))',
        r'(perplex.*(squad|team)|squad.*(team|perplex))',
        r'(you.*created by|created by.*you)',
        r'^(thanks?|thank you|thx|ty|cheers|appreciate it?)[!.,?\s]*$',
        r'^(ok|okay|got it|understood|sure|alright|great|nice|cool|awesome|perfect|wow)[!.,?\s]*$',
        r'^(no|nope|nah|yes|yeah|yep|correct|exactly|right|wrong|really)[!.,?\s]*$',
        r'^(not really|of course|absolutely|definitely)[!.,?\s]*$',
        r'^(bye|goodbye|see you|cya|later|good night)[!.,?\s]*$',
        r'^what (can|do) you (do|help|assist)[?!.,\s]*$',
        r'^help( me)?[?!.,\s]*$',
    ]
]

_FOLLOWUP_SIGNALS = frozenset({
    "again", "more", "full", "whole", "same",
    "above", "those", "that", "them", "repeat", "previous", "earlier", "all of",
    "list them", "show me", "tell me", "give me", "what about", "any more",
    "continue", "summarize", "summary"
})

_TOPIC_ANCHOR_RE = re.compile(
    r'\b(HCLSM-\d+|\d{4}|PDA|VIA|WEXLOG|COES|FIELDEAS|CONTINENTAL|SUPERVISOR|JASPER|ZEBRA|CEE)\b',
    re.IGNORECASE
)

_SORT_SIGNALS = frozenset({
    "ascending", "descending", "recent", "latest", "oldest",
    "order", "date", "created", "chronological", "last 10", "first", "sorted"
})


class RAGEngine:
    """RAG retrieval and generation engine."""

    def _compute_top_k(self, query: str, base_top_k: int) -> int:
        """Dynamically increase top_k for exhaustive listing queries."""
        if _LIST_SIGNALS_RE.search(query):
            boosted = min(base_top_k * settings.listing_query_boost, settings.listing_query_max_k)
            logger.info(f"Listing query detected — boosting top_k {base_top_k} -> {boosted}")
            return boosted
        return base_top_k

    def retrieve(self, query: str, top_k: int = None, use_reranking: bool = None) -> Tuple[str, List[str], Any, List[Dict]]:
        """Retrieve relevant context from both JIRA and PDF collections."""
        if top_k is None:
            top_k = max(settings.top_k_results, 15)
        top_k = self._compute_top_k(query, top_k)

        filter_dict = self._extract_metadata_filter(query)

        jira_results, rerank_summary = self._retrieve_jira(query, top_k, filter_dict, use_reranking)
        pdf_results = self._retrieve_pdf(query, top_k)

        all_docs, all_metas = self._merge_results(jira_results, pdf_results)

        if not all_docs:
            logger.warning("No relevant documents found in either collection")
            return "", [], None, []

        docs, metas = self._sort_by_date_if_needed(query, all_docs, all_metas)

        context, sources, citations = self._build_context(docs, metas)
        return context, sources, rerank_summary, citations

    def _extract_metadata_filter(self, query: str) -> dict | None:
        """Extract pre-retrieval metadata filter from query."""
        try:
            from services.jira.query_metadata_extractor import extract_query_metadata
            extracted = extract_query_metadata(query)
            if extracted:
                logger.info(f"Applying pre-retrieval metadata filter: {extracted}")
                return extracted
        except Exception as e:
            logger.debug(f"Metadata extraction skipped: {e}")
        return None

    def _retrieve_jira(self, query: str, top_k: int, filter_dict: dict | None, use_reranking: bool | None) -> Tuple[dict | None, Any]:
        """Retrieve from JIRA collection using hybrid or dense-only strategy."""
        try:
            from services.bm25_store import bm25_store
            from services.hybrid_retriever import HybridRetriever
            if bm25_store.is_ready():
                logger.info(f"Using HybridRetriever (BM25={bm25_store.count()} tickets) + CrossEncoder")
                hybrid = HybridRetriever(jira_vector_store, bm25_store)
                retriever = CrossEncoderRetriever(jira_vector_store)
                fused = hybrid.retrieve(query, top_k=top_k, filter_dict=filter_dict)
                results = retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict,
                                             precomputed_candidates=fused)
                return results, results.get('rerank_summary')
            else:
                logger.info("BM25 index empty — using dense-only on jira_vector_store")
                retriever = get_retriever(settings, jira_vector_store, use_reranking=use_reranking)
                return retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict), None
        except Exception as e:
            logger.debug(f"JIRA retrieval error, falling back to dense: {e}")
            try:
                retriever = get_retriever(settings, jira_vector_store, use_reranking=use_reranking)
                return retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict), None
            except Exception:
                return None, None

    def _retrieve_pdf(self, query: str, top_k: int) -> dict | None:
        """Retrieve from PDF/document collection using dense search."""
        try:
            pdf_retriever = get_retriever(settings, vector_store, use_reranking=False)
            results = pdf_retriever.retrieve(query, top_k=top_k)
            if results and results.get('documents'):
                logger.info("PDF collection returned results")
            return results
        except Exception as e:
            logger.debug(f"PDF retrieval error: {e}")
            return None

    @staticmethod
    def _safe_docs(res: dict | None) -> Tuple[List, List]:
        """Unwrap nested ChromaDB result format into flat lists."""
        if not res or not res.get('documents'):
            return [], []
        docs = res['documents']
        metas = res['metadatas']
        if docs and isinstance(docs[0], list):
            docs = docs[0]
            metas = metas[0] if metas else []
        return docs, metas

    def _merge_results(self, jira_results: dict | None, pdf_results: dict | None) -> Tuple[List, List]:
        """Merge JIRA and PDF result sets."""
        jdocs, jmetas = self._safe_docs(jira_results)
        pdocs, pmetas = self._safe_docs(pdf_results)
        return jdocs + pdocs, jmetas + pmetas

    def _sort_by_date_if_needed(self, query: str, docs: List, metas: List) -> Tuple[List, List]:
        """Sort results by date if the query contains sort signals."""
        query_lower = query.lower()
        if not any(sig in query_lower for sig in _SORT_SIGNALS) or not metas:
            return docs, metas

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
        logger.info(f"Sorted {len(docs)} chunks by date")
        return [p[0] for p in paired], [p[1] for p in paired]

    def _build_context(self, docs: List, metas: List) -> Tuple[str, List[str], List[Dict]]:
        """Build context string and consolidated citation list."""
        context_parts = []
        sources = []
        citations_map = {}
        source_ref_to_index = {}

        for doc, metadata in zip(docs, metas):
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

            if source_ref not in source_ref_to_index:
                source_ref_to_index[source_ref] = len(source_ref_to_index) + 1
                sources.append(source_ref)

            s_idx = source_ref_to_index[source_ref]
            context_parts.append(f"[[ SOURCE_S{s_idx} ]] (Data ID: {source_label})\n{doc}\n")

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
                if len(cite["snippet"]) < 1200:
                    cite["snippet"] += f"\n\n... [Cont'd (S{s_idx})] ...\n\n{doc[:400].strip()}"
                cite["metadata"]["count"] += 1
                page = metadata.get('page')
                if page and page not in cite["metadata"]["pages"]:
                    cite["metadata"]["pages"].append(page)

        citations = sorted(citations_map.values(), key=lambda x: x["metadata"]["source_index"])
        logger.info(f"Retrieved {len(docs)} chunks, consolidated into {len(citations)} source cards")
        return "\n".join(context_parts), sources, citations

    def generate_answer(
        self,
        query: str,
        context: str,
        session_id: str,
        conversation_history: List[Dict[str, str]] = None,
        use_knowledge_base: bool = True
    ) -> Tuple[str, Dict]:
        """Generate an answer using RAG and semantic memory."""
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

        full_context = context
        if memory_str:
            full_context = f"{memory_str}\n\nDocument Context:\n{context}" if context else memory_str

        response, gen_metrics = bedrock_client.generate_response(
            user_message=query,
            context=full_context,
            conversation_history=conversation_history,
            use_knowledge_base=use_knowledge_base
        )

        return response, gen_metrics

    def _contextualize_query(self, query: str, conversation_history: List[Dict[str, str]]) -> str:
        """Expand a follow-up question with context from conversation history."""
        query_lower = query.lower().strip()
        is_short = len(query.split()) <= settings.short_query_word_limit
        has_signal = any(sig in query_lower for sig in _FOLLOWUP_SIGNALS)
        has_topic = bool(_TOPIC_ANCHOR_RE.search(query))

        if is_short and has_signal and not has_topic and conversation_history:
            last_user_query = None
            for msg in reversed(conversation_history):
                if msg.get("role") == "user":
                    last_user_query = msg.get("content", "").strip()
                    break

            if last_user_query and last_user_query.lower() != query_lower:
                expanded = f"{last_user_query} {query}"
                logger.info(f"ContextualizedQuery: '{query}' -> '{expanded[:120]}'")
                return expanded

        return query

    def _is_casual_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> bool:
        """Detect whether a query is casual/conversational and does NOT need RAG retrieval."""
        q = query.strip().lower()

        if _IT_SIGNALS_RE.search(query):
            logger.debug(f"IT signal detected — will retrieve: '{query[:80]}'")
            return False

        for pattern in _CASUAL_PATTERNS:
            if pattern.search(q):
                logger.debug(f"Casual pattern match — skipping retrieval: '{query[:80]}'")
                return True

        word_count = len(query.split())
        if word_count <= settings.casual_query_word_limit:
            logger.debug(f"Short non-IT query ({word_count}w) — skipping retrieval: '{query[:80]}'")
            return True

        return False

    def _build_metrics(self, t0: float, retrieval_s: float, gen_m: Dict, query_type: str, sources_count: int) -> Dict:
        """Build standardized metrics dict."""
        return {
            "latency_s":        round(time.time() - t0, 3),
            "retrieval_s":      retrieval_s,
            "generation_s":     gen_m.get("generation_s", 0.0),
            "input_tokens":     gen_m.get("input_tokens", 0),
            "output_tokens":    gen_m.get("output_tokens", 0),
            "total_tokens":     gen_m.get("total_tokens", 0),
            "query_type":       query_type,
            "sources_retrieved": sources_count,
        }

    def chat(
        self,
        query: str,
        session_id: str,
        conversation_history: List[Dict[str, str]] = None,
        use_knowledge_base: bool = True,
        use_reranking: bool = None
    ) -> Tuple[str, List[str], Any, Dict, List]:
        """Complete RAG chat: retrieve context and generate answer."""
        t0 = time.time()

        # Step 1: Detect casual intent
        if use_knowledge_base and self._is_casual_query(query, conversation_history):
            logger.info(f"Casual query detected — bypassing retrieval: '{query[:80]}'")
            answer, gen_m = self.generate_answer(query, "", session_id, conversation_history, use_knowledge_base=False)
            return answer, [], None, self._build_metrics(t0, 0.0, gen_m, "casual", 0), []

        # Step 2: Build retrieval query anchored to conversation topic
        retrieval_query = query
        if use_knowledge_base and conversation_history:
            retrieval_query = self._contextualize_query(query, conversation_history)

        # Step 3: Retrieve context + citations
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

        return answer, sources, rerank_summary, self._build_metrics(t0, retrieval_s, gen_m, "rag", len(sources)), citations


# Global RAG engine instance
rag_engine = RAGEngine()

"""
Hybrid retriever: Dense (Titan) + BM25 (rank_bm25) with Reciprocal Rank Fusion.

Pipeline:
    1. Dense search  → top_k candidates via ChromaDB
    2. BM25 search   → top_k candidates via rank_bm25
    3. RRF fusion    → merged, deduplicated, and re-scored top_k list
    4. (Caller)      → Cross-Encoder reranks the fused list

RRF formula:  score(d) = Σ  1 / (k + rank_i(d))
              k = 60 (standard constant; dampens rank 1 dominance)
"""
import concurrent.futures
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_RRF_K = 60  # Standard RRF constant


def rrf_fusion(
    dense_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    k: int = _RRF_K,
    top_k: int = 50,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.2,
) -> List[Dict[str, Any]]:
    """
    Merge dense and BM25 result lists using Weighted Reciprocal Rank Fusion.

    score(d) = dense_weight / (k + rank_dense) 
             + sparse_weight / (k + rank_bm25)

    Sparse weight defaults to 1.2 (> dense 1.0) because BM25 has higher
    precision for exact identifiers (error codes, ticket IDs, IP addresses).

    Each result dict must have:
        - 'ticket_id'  (for deduplication)
        - 'text'
        - 'metadata'

    Dense results may include multiple entries per ticket (symptom + resolution
    vectors). We keep the highest-ranked vector per ticket for the dense side.

    Args:
        dense_results:  Ordered list from Chroma/vector similarity search.
        bm25_results:   Ordered list from OpenSearch BM25 search.
        k:              RRF damping constant (default 60).
        top_k:          Maximum fused results to return.
        dense_weight:   Multiplier for dense retrieval ranks.
        sparse_weight:  Multiplier for BM25 ranks (default higher than dense).

    Returns:
        Merged list sorted by weighted RRF score descending, up to top_k.
    """
    scores: Dict[str, float] = {}
    docs: Dict[str, Dict[str, Any]] = {}

    def _add(results: List[Dict[str, Any]], weight: float) -> None:
        seen = {}
        for rank, result in enumerate(results):
            tid = result.get("ticket_id") or result.get("metadata", {}).get("ticket_id", "")
            if not tid or tid in seen:
                continue
            seen[tid] = rank
            scores[tid] = scores.get(tid, 0.0) + weight / (k + rank)
            if tid not in docs:
                docs[tid] = result

    _add(dense_results, dense_weight)
    _add(bm25_results, sparse_weight)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    result_list = []
    for i, (tid, score) in enumerate(fused[:top_k]):
        entry = dict(docs[tid])
        entry["rrf_score"] = score
        entry["rrf_rank"]  = i + 1
        result_list.append(entry)

    logger.info(
        "Weighted RRF fusion complete",
        extra={
            "dense_inputs":  len(dense_results),
            "bm25_inputs":   len(bm25_results),
            "fused_outputs": len(result_list),
            "dense_weight":  dense_weight,
            "sparse_weight": sparse_weight,
        },
    )
    return result_list



class HybridRetriever:
    """
    Runs dense and BM25 search in parallel threads, then fuses with RRF.

    The output is a flat list of candidates that the CrossEncoderRetriever
    (or VectorRetriever) can rerank. We convert the fused list into the
    standard ChromaDB result format for seamless compatibility with existing
    retriever and rag_engine code.
    """

    def __init__(self, vector_store, bm25_store):
        self.vector_store = vector_store
        self.bm25_store = bm25_store

    def retrieve(
        self,
        query: str,
        top_k: int = 50,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Hybrid retrieval: Dense ∥ BM25 → RRF → ChromaDB-compatible result dict.

        Args:
            query:       User query string.
            top_k:       Number of fused candidates to return.
            filter_dict: Metadata pre-filter (passed to both retrievers).

        Returns:
            Dict with 'documents', 'metadatas', 'ids' lists (ChromaDB format).
        """
        logger.info(f"HybridRetriever: parallel dense+BM25 search (top_k={top_k})")

        dense_results: List[Dict[str, Any]] = []
        bm25_results: List[Dict[str, Any]] = []

        def _dense_search() -> None:
            raw = self.vector_store.search(query, top_k=top_k, filter_dict=filter_dict)
            docs = raw.get("documents", [])
            metas = raw.get("metadatas", [])
            # Unpack nested list (ChromaDB may nest)
            if docs and isinstance(docs[0], list):
                docs = docs[0]
                metas = metas[0] if metas else []
            for doc, meta in zip(docs, metas):
                dense_results.append({
                    "ticket_id": meta.get("ticket_id", ""),
                    "text":      doc,
                    "metadata":  meta,
                })

        def _bm25_search() -> None:
            results = self.bm25_store.search(query, top_k=top_k, filter_dict=filter_dict)
            bm25_results.extend(results)

        # Run both retrievers in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_dense = executor.submit(_dense_search)
            f_bm25 = executor.submit(_bm25_search)
            for future in concurrent.futures.as_completed([f_dense, f_bm25]):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Retrieval branch failed: {e}")

        # Fuse results
        fused = rrf_fusion(dense_results, bm25_results, top_k=top_k)

        if not fused:
            return {"documents": [], "metadatas": []}

        # Convert to ChromaDB-compatible format
        return {
            "documents": [r["text"] for r in fused],
            "metadatas": [r["metadata"] for r in fused],
        }

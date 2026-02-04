"""
Retriever abstractions for RAG.
Implements Strategy pattern for retrieval mechanisms.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

# Global cache for the Cross-Encoder model to prevent repeated reloads
_GLOBAL_MODEL_CACHE = {}

class Retriever(ABC):
    """Abstract base class for retrievers."""
    
    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> Dict[str, Any]:
        """
        Retrieve documents matching the query.
        
        Args:
            query: User search query
            top_k: Number of final results to return
            
        Returns:
            Dictionary containing 'documents' (list of strings) and 'metadatas' (list of dicts)
        """
        pass


class VectorRetriever(Retriever):
    """
    Standard vector similarity search retriever.
    Wraps existing vector_store functionality.
    """
    
    def __init__(self, vector_store):
        self.vector_store = vector_store
        
    def retrieve(self, query: str, top_k: int) -> Dict[str, Any]:
        """Direct vector similarity search."""
        logger.info(f"VectorRetriever executing search for: {query} (k={top_k})")
        return self.vector_store.search(query, top_k=top_k)


class CrossEncoderRetriever(Retriever):
    """
    Two-stage retriever with Cross-Encoder reranking.
    Stage 1: Retrieve large candidate set (top_k * factor or fixed large number) via vector search.
    Stage 2: Rerank candidates using a Cross-Encoder model.
    """
    
    def __init__(self, vector_store, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        from app.config import settings
        self.vector_store = vector_store
        self.model_name = model_name
        self.stage1_k = settings.top_k_stage1 # Fetch candidates for reranking from settings
        
    @property
    def model(self):
        """Lazy loader for the CrossEncoder model with global caching."""
        global _GLOBAL_MODEL_CACHE
        if self.model_name not in _GLOBAL_MODEL_CACHE:
            logger.info(f"Loading CrossEncoder model: {self.model_name}")
            try:
                from sentence_transformers import CrossEncoder
                _GLOBAL_MODEL_CACHE[self.model_name] = CrossEncoder(self.model_name)
            except Exception as e:
                logger.error(f"Failed to load CrossEncoder model: {e}")
                raise e
        return _GLOBAL_MODEL_CACHE[self.model_name]
        
    def retrieve(self, query: str, top_k: int) -> Dict[str, Any]:
        """Retrieve candidates and rerank them with detailed audit logging."""
        import time
        start_time = time.time()
        
        # Stage 1: Vector Search (Candidate Generation)
        logger.info(f"🔍 [Rerank] Stage 1: Fetching {self.stage1_k} candidates from Vector Store")
        candidates = self.vector_store.search(query, top_k=self.stage1_k, threshold=1000.0)
        
        if not candidates['documents']:
            return candidates
            
        docs = candidates['documents'][0] if isinstance(candidates['documents'][0], list) else candidates['documents']
        metadatas = candidates['metadatas'][0] if isinstance(candidates['metadatas'][0], list) else candidates['metadatas']
        
        if len(docs) == 0:
            return {'documents': [], 'metadatas': []}

        # Stage 2: Reranking
        logger.info(f"🧠 [Rerank] Stage 2: Passing {len(docs)} candidates to Cross-Encoder")
        
        # Prepare pairs for scoring: (query, doc_text)
        pairs = [[query, doc_text] for doc_text in docs]
        
        # Score pairs
        scores = self.model.predict(pairs)
        
        # Pair up scores with content indices and initial rank
        scored_results = []
        for idx, score in enumerate(scores):
            scored_results.append({
                'score': float(score),
                'doc': docs[idx],
                'metadata': metadatas[idx],
                'initial_rank': idx + 1
            })
            
        # Sort by score descending
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        # Log Summary
        logger.info("📊 --- Reranking Impact Summary ---")
        for i, res in enumerate(scored_results[:top_k]):
            new_rank = i + 1
            jump = res['initial_rank'] - new_rank
            arrow = "↑" if jump > 0 else ("↓" if jump < 0 else "-")
            jump_val = abs(jump) if jump != 0 else ""
            
            fname = res['metadata'].get('filename', 'Unknown')[:20]
            logger.info(f"Final Rank {new_rank}: {fname}... [Score: {res['score']:.4f}] (Was Rank {res['initial_rank']} {arrow}{jump_val})")
        
        # Select final top_k
        final_results = scored_results[:top_k]
        
        # Prepare structured summary for API response
        rerank_summary = [
            {
                "initial_rank": r["initial_rank"],
                "final_rank": i + 1,
                "score": r["score"],
                "filename": r["metadata"].get("filename", "Unknown"),
                "page": str(r["metadata"].get("page", "N/A"))
            }
            for i, r in enumerate(final_results)
        ]

        total_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ Reranking complete in {total_ms:.2f}ms")
        
        return {
            'documents': [r['doc'] for r in final_results],
            'metadatas': [r['metadata'] for r in final_results],
            'rerank_summary': rerank_summary
        }


def get_retriever(settings, vector_store, use_reranking: bool = None) -> Retriever:
    """Factory function to get the appropriate retriever based on settings or override."""
    # Use override if provided, otherwise fallback to global setting
    is_enabled = use_reranking if use_reranking is not None else settings.cross_encoder_enabled
    
    if is_enabled:
        return CrossEncoderRetriever(vector_store)
    else:
        return VectorRetriever(vector_store)

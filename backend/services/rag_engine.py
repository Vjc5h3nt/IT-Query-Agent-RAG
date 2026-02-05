"""RAG engine for retrieval and answer generation."""
from typing import List, Dict, Tuple, Any
from services.vector_store import vector_store
from services.bedrock_client import bedrock_client
from services.memory_service import memory_service
from services.retriever import get_retriever
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG retrieval and generation engine."""
    
    def retrieve(self, query: str, top_k: int = None, use_reranking: bool = None) -> Tuple[str, List[str], Any]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: User query
            top_k: Number of results to retrieve
            
        Returns:
            Tuple of (formatted_context, source_list)
        """
        if top_k is None:
            # We use 15 chunks to ensure coverage for multi-topic questions.
            top_k = max(settings.top_k_results, 15)
        
        # Get retriever based on settings or override
        retriever = get_retriever(settings, vector_store, use_reranking=use_reranking)
        
        # Execute retrieval
        results = retriever.retrieve(query, top_k=top_k)
        
        if not results['documents']:
            logger.warning("No relevant documents found")
            return "", [], None
        
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

        for i, (doc, metadata) in enumerate(zip(docs, metas), 1):
            filename = metadata.get('filename', 'Unknown')
            page = metadata.get('page', 'N/A')
            
            # Format each chunk with source info
            context_parts.append(
                f"[Source {i}: {filename}, Page {page}]\n{doc}\n"
            )
            
            # Track unique sources
            source_ref = f"{filename} (Page {page})"
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
        # Step 1: Retrieve relevant context (only if enabled)
        context = ""
        sources = []
        rerank_summary = None
        if use_knowledge_base:
            context, sources, rerank_summary = self.retrieve(query, use_reranking=use_reranking)
        
        # Step 2: Generate answer
        answer = self.generate_answer(query, context, session_id, conversation_history, use_knowledge_base)
        
        return answer, sources, rerank_summary


# Global RAG engine instance
rag_engine = RAGEngine()

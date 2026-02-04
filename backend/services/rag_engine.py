"""RAG engine for retrieval and answer generation."""
from typing import List, Dict, Tuple
from services.vector_store import vector_store
from services.bedrock_client import bedrock_client
from services.memory_service import memory_service
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG retrieval and generation engine."""
    
    def retrieve(self, query: str, top_k: int = None) -> Tuple[str, List[str]]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: User query
            top_k: Number of results to retrieve
            
        Returns:
            Tuple of (formatted_context, source_list)
        """
        if top_k is None:
            top_k = settings.top_k_results
        
        # Search vector store
        results = vector_store.search(query, top_k=top_k)
        
        if not results['documents']:
            logger.warning("No relevant documents found")
            return "", []
        
        # Format context from retrieved chunks
        context_parts = []
        sources = []
        
        for i, (doc, metadata) in enumerate(zip(results['documents'], results['metadatas']), 1):
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
        
        formatted_context = "\n".join(context_parts)
        
        logger.info(f"Retrieved {len(results['documents'])} chunks from {len(sources)} sources")
        logger.debug(f"Retrieved Context Preview: {formatted_context[:500]}...")
        return formatted_context, sources
    
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
        use_knowledge_base: bool = True
    ) -> Tuple[str, List[str]]:
        """
        Complete RAG chat: retrieve context and generate answer.
        
        Args:
            query: User query
            session_id: Current session ID
            conversation_history: Previous messages
            use_knowledge_base: Whether to use the vector knowledge base
            
        Returns:
            Tuple of (answer, sources)
        """
        # Step 1: Retrieve relevant context (only if enabled)
        context = ""
        sources = []
        if use_knowledge_base:
            context, sources = self.retrieve(query)
        
        # Step 2: Generate answer
        answer = self.generate_answer(query, context, session_id, conversation_history, use_knowledge_base)
        
        return answer, sources


# Global RAG engine instance
rag_engine = RAGEngine()

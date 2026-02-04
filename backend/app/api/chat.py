"""Chat API endpoints."""
from fastapi import APIRouter, HTTPException
from app.models import ChatRequest, ChatResponse, ChatMessage
from services.rag_engine import rag_engine
from services.session_manager import session_manager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Send a message and get RAG-based response.
    
    Args:
        request: Chat request with session_id and message
        
    Returns:
        Chat response with user message, assistant message, and sources
    """
    try:
        # Verify session exists
        session = session_manager.get_session_detail(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get conversation history from LangChain memory (last 5 messages)
        conversation_history = session_manager.get_conversation_history(request.session_id)
        
        # Add user message to session
        session_manager.add_user_message(request.session_id, request.message)
        
        # Initialize session memories if it's the first turn (optional, but requested by user pattern)
        from services.memory_service import memory_service
        existing_memories = memory_service.get_memories(request.session_id)
        if not existing_memories:
            memory_service.put_memory(
                request.session_id, 
                "preferences", 
                {"rules": ["User likes short, direct language", "User only speaks English & Python"]}
            )

        # Generate RAG response
        answer, sources = rag_engine.chat(
            query=request.message,
            session_id=request.session_id,
            conversation_history=conversation_history,
            use_knowledge_base=request.use_knowledge_base
        )
        
        # Add assistant message to session
        session_manager.add_assistant_message(request.session_id, answer)
        
        # Create response
        user_msg = ChatMessage(
            role="user",
            content=request.message,
            timestamp=datetime.utcnow()
        )
        
        assistant_msg = ChatMessage(
            role="assistant",
            content=answer,
            timestamp=datetime.utcnow()
        )
        
        response = ChatResponse(
            session_id=request.session_id,
            user_message=user_msg,
            assistant_message=assistant_msg,
            sources=sources
        )
        
        logger.info(f"Chat response generated for session {request.session_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

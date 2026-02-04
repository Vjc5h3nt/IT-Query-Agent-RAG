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
        
        # Get conversation history (last 5 messages)
        conversation_history = session_manager.get_conversation_history(request.session_id)
        is_first_message = len(conversation_history) == 0
        
        # Add user message to session
        session_manager.add_user_message(request.session_id, request.message)
        
        if is_first_message:
            # Generate a descriptive name like ChatGPT
            session_manager.auto_name_session(request.session_id, request.message)
        
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
        answer, sources, rerank_summary = rag_engine.chat(
            query=request.message,
            session_id=request.session_id,
            conversation_history=conversation_history,
            use_knowledge_base=request.use_knowledge_base,
            use_reranking=request.use_reranking
        )
        
        # Add assistant message to session
        session_manager.add_assistant_message(request.session_id, answer, rerank_summary=rerank_summary)
        
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
            sources=sources,
            rerank_summary=rerank_summary
        )
        
        logger.info(f"Chat response generated for session {request.session_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "ExpiredTokenException" in error_msg:
            logger.error(f"AWS Credentials Expired: {error_msg}")
            raise HTTPException(status_code=401, detail="AWS credentials have expired. Please refresh your AWS token.")
        elif "UnrecognizedClientException" in error_msg:
            logger.error(f"Invalid AWS Credentials: {error_msg}")
            raise HTTPException(status_code=401, detail="Invalid AWS credentials. Please check your AWS configuration.")
        
        logger.error(f"Error in chat endpoint: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

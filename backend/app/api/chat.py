"""Chat API endpoints."""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.models import ChatMessage, ChatRequest, ChatResponse, ResponseMetrics
from services.memory_service import memory_service
from services.rag_engine import rag_engine
from services.session_manager import session_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# AWS credential error signatures
_AWS_CREDENTIAL_ERRORS = {
    "ExpiredTokenException": "AWS credentials have expired. Please refresh your AWS token.",
    "UnrecognizedClientException": "Invalid AWS credentials. Please check your AWS configuration.",
}


@router.post("", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a message and get RAG-based response."""
    try:
        session = session_manager.get_session_detail(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        conversation_history = session_manager.get_conversation_history(
            request.session_id,
            context_messages=request.context_messages
        )
        is_first_message = len(conversation_history) == 0

        session_manager.add_user_message(request.session_id, request.message)

        if is_first_message:
            session_manager.auto_name_session(request.session_id, request.message)
            _init_session_memory(request.session_id)

        answer, sources, rerank_summary, raw_metrics, citations = rag_engine.chat(
            query=request.message,
            session_id=request.session_id,
            conversation_history=conversation_history,
            use_knowledge_base=request.use_knowledge_base,
            use_reranking=request.use_reranking
        )

        metrics_obj = ResponseMetrics(**raw_metrics) if raw_metrics else None

        session_manager.add_assistant_message(
            request.session_id,
            answer,
            rerank_summary=rerank_summary,
            metrics=raw_metrics,
            citations=citations
        )

        now = datetime.utcnow()
        response = ChatResponse(
            session_id=request.session_id,
            user_message=ChatMessage(role="user", content=request.message, timestamp=now),
            assistant_message=ChatMessage(role="assistant", content=answer, timestamp=now, metrics=raw_metrics, citations=citations),
            sources=sources,
            rerank_summary=rerank_summary,
            metrics=metrics_obj,
            citations=citations
        )

        logger.info(f"Chat response generated for session {request.session_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        for error_key, user_message in _AWS_CREDENTIAL_ERRORS.items():
            if error_key in error_msg:
                logger.error(f"AWS Credentials Error: {error_msg}")
                raise HTTPException(status_code=401, detail=user_message)

        logger.error(f"Error in chat endpoint: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


def _init_session_memory(session_id: str) -> None:
    """Initialize default session memory if none exists."""
    existing = memory_service.get_memories(session_id)
    if not existing:
        memory_service.put_memory(
            session_id,
            "preferences",
            {"rules": ["User likes short, direct language", "User only speaks English & Python"]}
        )

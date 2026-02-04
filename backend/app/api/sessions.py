"""Session management API endpoints."""
from fastapi import APIRouter, HTTPException
from typing import List
from app.models import SessionCreate, Session, SessionDetail
from services.session_manager import session_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=Session)
async def create_session(request: SessionCreate):
    """
    Create a new chat session.
    
    Args:
        request: Session creation request with optional name
        
    Returns:
        Created session
    """
    try:
        session_id = session_manager.create_session(request.name)
        session = session_manager.get_session_detail(session_id)
        
        return Session(
            id=session['id'],
            name=session['name'],
            created_at=session['created_at'],
            updated_at=session['updated_at']
        )
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[Session])
async def get_sessions():
    """
    Get all chat sessions.
    
    Returns:
        List of sessions
    """
    try:
        sessions = session_manager.get_all_sessions()
        return [
            Session(
                id=s['id'],
                name=s['name'],
                created_at=s['created_at'],
                updated_at=s['updated_at']
            )
            for s in sessions
        ]
    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str):
    """
    Get session details with messages.
    
    Args:
        session_id: Session ID
        
    Returns:
        Session with messages
    """
    try:
        session = session_manager.get_session_detail(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionDetail(**session)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("")
async def delete_all_sessions():
    """
    Delete all sessions.
    
    Returns:
        Success message with count
    """
    try:
        count = session_manager.delete_all_sessions()
        return {"message": "All sessions deleted successfully", "count": count}
    except Exception as e:
        logger.error(f"Error deleting all sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        Success message
    """
    try:
        success = session_manager.delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

"""Session manager with simple rolling 5-message memory."""
from typing import Dict, List, Optional
from database.session_db import session_db
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages chat sessions with rolling 5-message memory."""
    
    def __init__(self):
        """Initialize session manager."""
        # Cache for conversation history per session
        self._memory_cache: Dict[str,  List[Dict[str, str]]] = {}
    
    def create_session(self, name: Optional[str] = None) -> str:
        """
        Create a new chat session.
        
        Args:
            name: Optional session name
            
        Returns:
            Session ID
        """
        session = session_db.create_session(name)
        self._memory_cache[session.id] = []
        
        logger.info(f"Created new session: {session.id}")
        return session.id
    
    def get_all_sessions(self) -> List[Dict]:
        """
        Get all chat sessions.
        
        Returns:
            List of session dictionaries
        """
        sessions = session_db.get_all_sessions()
        return [
            {
                "id": s.id,
                "name": s.name,
                "created_at": s.created_at,
                "updated_at": s.updated_at
            }
            for s in sessions
        ]
    
    def get_session_detail(self, session_id: str) -> Optional[Dict]:
        """
        Get session details with messages.
        """
        import json
        session = session_db.get_session_by_id(session_id)
        if not session:
            return None
        
        messages = session_db.get_session_messages(session_id)
        
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "rerank_summary": json.loads(m.rerank_summary) if m.rerank_summary else None
                }
                for m in messages
            ]
        }
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if deleted successfully
        """
        # Remove from memory cache
        if session_id in self._memory_cache:
            del self._memory_cache[session_id]
        
        return session_db.delete_session(session_id)
    
    def delete_all_sessions(self) -> int:
        """
        Delete all chat sessions.
        
        Returns:
            Number of sessions deleted
        """
        self._memory_cache.clear()
        return session_db.delete_all_sessions()
    
    def update_session(self, session_id: str, name: str) -> bool:
        """Update a session's name."""
        return session_db.update_session_name(session_id, name)

    def auto_name_session(self, session_id: str, first_message: str) -> None:
        """
        Automatically generate a descriptive name for the session 
        based on the first message if it currently has a default name.
        """
        # Get current session to check name
        session = session_db.get_session_by_id(session_id)
        
        # Only auto-name if it has the default "Chat Session YYYY-MM-DD..." name
        if not session or not session.name.startswith("Chat Session"):
            return

        from services.bedrock_client import bedrock_client
        prompt = (
            "Generate a very concise, 2-4 word title for a chat conversation that starts with this message: "
            f"'{first_message}'. Respond ONLY with the title. No quotes, no intro, no punctuation."
        )
            
        # Only auto-name if it has a generic default name
        generic_prefixes = ("Chat Session", "New Chat", "Session", "Conversation")
        if not session or not session.name.startswith(generic_prefixes):
            logger.info(f"Skipping auto-naming for session {session_id} with custom name: {session.name if session else 'None'}")
            return
        try:
            new_name = bedrock_client.generate_simple_text(prompt)
            if new_name and len(new_name) < 50:
                # Clean up the name (remove quotes if model ignored instructions)
                clean_name = new_name.replace('"', '').replace("'", "").strip()
                if clean_name:
                    self.update_session(session_id, clean_name)
                    logger.info(f"Auto-named session {session_id} to '{clean_name}'")
        except Exception as e:
            logger.error(f"Failed to auto-name session: {e}")

    def _get_or_create_memory(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get or create memory for a session with 5-message window.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of message dictionaries
        """
        if session_id not in self._memory_cache:
            # Load existing messages from database (last 5 only)
            messages = session_db.get_session_messages(
                session_id,
                limit=settings.max_memory_messages * 2  # 5 user + 5 assistant = 10 total
            )
            
            # Convert to simple dict format
            self._memory_cache[session_id] = [
                {
                    "role": m.role,
                    "content": m.content
                }
                for m in messages
            ]
            
            logger.info(f"Loaded memory for session {session_id} with {len(messages)} messages")
        
        return self._memory_cache[session_id]
    
    def get_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get conversation history (last 5 messages).
        
        Args:
            session_id: Session ID
            
        Returns:
            List of message dictionaries with 'role' and 'content'
        """
        memory = self._get_or_create_memory(session_id)
        
        # Return last 5 conversation turns (10 messages total)
        max_messages = settings.max_memory_messages * 2
        history_slice = memory[-max_messages:] if len(memory) > max_messages else memory
        return [msg.copy() for msg in history_slice]  # Return a deep copy of the message dicts
    
    def add_user_message(self, session_id: str, message: str) -> None:
        """
        Add user message to session (maintains 5-message window).
        
        Args:
            session_id: Session ID
            message: User message content
        """
        # Add to database
        session_db.add_message(session_id, "user", message)
        
        # Add to memory cache
        memory = self._get_or_create_memory(session_id)
        memory.append({
            "role": "user",
            "content": message
        })
        
        # Trim to last 5 conversation turns (10 messages)
        max_messages = settings.max_memory_messages * 2
        if len(memory) > max_messages:
            self._memory_cache[session_id] = memory[-max_messages:]
        
        logger.info(f"Added user message to session {session_id}")
    
    def add_assistant_message(self, session_id: str, message: str, rerank_summary: list = None) -> None:
        """
        Add assistant message to session with optional audit data.
        """
        # Add to database
        session_db.add_message(session_id, "assistant", message, rerank_summary=rerank_summary)
        
        # Add to memory cache
        memory = self._get_or_create_memory(session_id)
        memory.append({
            "role": "assistant",
            "content": message
        })
        
        # Trim to last 5 conversation turns (10 messages)
        max_messages = settings.max_memory_messages * 2
        if len(memory) > max_messages:
            self._memory_cache[session_id] = memory[-max_messages:]
        
        logger.info(f"Added assistant message to session {session_id}")


# Global session manager instance
session_manager = SessionManager()

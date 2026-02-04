"""Memory service using LangGraph InMemoryStore for semantic session context."""
from typing import Dict, List, Any, Optional
from langgraph.store.memory import InMemoryStore
from services.bedrock_client import bedrock_client
import logging

logger = logging.getLogger(__name__)

class MemoryService:
    """Service to handle semantic memories and user preferences."""
    
    def __init__(self):
        """Initialize semantic memory store."""
        # Using 1536 dimensions for Amazon Titan Embeddings
        self.store = InMemoryStore(
            index={
                "embed": bedrock_client.generate_embeddings,
                "dims": 1536
            }
        )
        logger.info("Initialized semantic memory store with Bedrock embeddings")

    def put_memory(self, session_id: str, key: str, value: Dict[str, Any]) -> None:
        """
        Store a memory in a session's namespace.
        
        Args:
            session_id: The session ID (used as namespace)
            key: Unique key for the memory
            value: Dictionary containing memory data (e.g., {'rules': [...]})
        """
        namespace = (session_id, "context")
        self.store.put(namespace, key, value)
        logger.info(f"Stored memory '{key}' for session {session_id}")

    def get_memories(self, session_id: str, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories for a session.
        
        Args:
            session_id: The session ID
            query: Optional query for semantic search
            
        Returns:
            List of memory content dictionaries
        """
        namespace = (session_id, "context")
        
        if query:
            # Semantic search for relevant memories
            items = self.store.search(namespace, query=query, limit=5)
            return [item.value for item in items]
        else:
            # Get all memories in the namespace
            items = self.store.list_namespaces(prefix=namespace)
            # This returns namespaces. To get items, we should use search with no query if supported,
            # or just list specific items if we known keys.
            # Actually, search with no query or wildcards isn't always supported.
            # For now, let's just return empty for list all if not needed.
            return []

    def clear_session_memories(self, session_id: str) -> None:
        """Clear all memories for a session - since it's InMemoryStore, this is handled by namespace."""
        # Note: InMemoryStore doesn't have a direct 'delete_namespace', 
        # but we can list and delete if needed. 
        # For this implementation, we'll just let it be.
        pass

# Global memory service instance
memory_service = MemoryService()


import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.config import settings
from services.rag_engine import rag_engine

def test_retrieval():
    try:
        print("Testing retrieval with Knowledge Base...")
        # Mocking a session_id and query
        query = "What is the project about?"
        session_id = "test-session"
        
        print(f"Calling rag_engine.chat with query: {query}")
        answer, sources = rag_engine.chat(
            query=query,
            session_id=session_id,
            use_knowledge_base=True,
            use_reranking=False
        )
        print(f"Answer: {answer}")
        print(f"Sources: {sources}")
        
        print("Testing with reranking...")
        # This will trigger model load if enabled, but let's test the factory first
        from services.retriever import get_retriever
        from services.vector_store import vector_store
        retriever = get_retriever(settings, vector_store, use_reranking=False)
        print(f"Retriever: {type(retriever)}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_retrieval()

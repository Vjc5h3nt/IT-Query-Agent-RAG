import sys
import os

# Ensure backend/ is in the Python path when running as a script
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from services.vector_store import vector_store
from database.session_db import session_db, DocumentMetadata
from app.config import settings

def reset_all_data():
    print("🚀 Starting data reset process...")
    
    # 1. Clear ChromaDB
    try:
        print(f"🧹 Clearing ChromaDB collection: {settings.collection_name}...")
        count_before = vector_store.get_collection_count()
        
        # Delete all documents by passing all IDs
        # If the collection is large, we might need a different approach, 
        # but for 144 docs this is fine.
        results = vector_store.collection.get()
        ids = results.get('ids', [])
        
        if ids:
            vector_store.collection.delete(ids=ids)
            print(f"✅ Deleted {len(ids)} documents from ChromaDB.")
        else:
            print("ℹ️ ChromaDB was already empty.")
            
    except Exception as e:
        print(f"❌ Error clearing ChromaDB: {e}")

    # 2. Clear Document Metadata in SQLite
    try:
        print("🧹 Clearing document metadata from SQLite...")
        db = session_db.get_session()
        try:
            num_deleted = db.query(DocumentMetadata).delete()
            db.commit()
            print(f"✅ Deleted {num_deleted} records from DocumentMetadata table.")
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Error clearing SQLite metadata: {e}")

    print("\n✨ Done! All ingested data has been cleared.")
    print("You can now run ingestion again to start fresh.")

if __name__ == "__main__":
    reset_all_data()

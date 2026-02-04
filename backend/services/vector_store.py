"""ChromaDB vector store for document embeddings."""
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
from app.config import settings
from services.bedrock_client import bedrock_client
import logging

logger = logging.getLogger(__name__)


class CustomEmbeddingFunction:
    """Custom embedding function using AWS Bedrock Titan."""
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts using optimized batch client."""
        return bedrock_client.generate_embeddings(input)


class VectorStore:
    """ChromaDB vector store manager."""
    
    def __init__(self):
        """Initialize ChromaDB with persistent storage."""
        chroma_path = settings.get_absolute_path(settings.chroma_db_path)
        
        self.client = chromadb.PersistentClient(
            path=chroma_path,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )
        
        self.embedding_function = CustomEmbeddingFunction()
        
        # Get or create collection - don't pass embedding function to avoid conflicts
        try:
            self.collection = self.client.get_collection(
                name=settings.collection_name
            )
            logger.info(f"Loaded existing collection: {settings.collection_name} ({self.collection.count()} documents)")
        except:
            self.collection = self.client.create_collection(
                name=settings.collection_name,
                metadata={"description": "RAG document chunks"}
            )
            logger.info(f"Created new collection: {settings.collection_name}")
    
    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ) -> None:
        """
        Add documents to the vector store.
        
        Args:
            texts: List of text chunks
            metadatas: List of metadata dicts for each chunk
            ids: List of unique IDs for each chunk
        """
        try:
            # Generate embeddings manually (now parallelized via bedrock_client)
            embeddings = self.embedding_function(texts)
            
            # Add to collection in smaller sub-batches to be safe (e.g., 500 at a time)
            batch_size = 500
            total_added = 0
            
            for i in range(0, len(texts), batch_size):
                end_idx = min(i + batch_size, len(texts))
                
                self.collection.add(
                    documents=texts[i:end_idx],
                    embeddings=embeddings[i:end_idx],
                    metadatas=metadatas[i:end_idx],
                    ids=ids[i:end_idx]
                )
                total_added += (end_idx - i)
                logger.info(f"Pushed {total_added}/{len(texts)} chunks to vector store...")

            logger.info(f"Successfully added {len(texts)} total documents to vector store")
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}")
            raise
    
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_dict: Optional[Dict[str, Any]] = None,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Search for relevant documents.
        
        Args:
            query: Search query
            top_k: Number of results to return (default from settings)
            filter_dict: Optional metadata filter
            threshold: Optional similarity threshold override
            
        Returns:
            Dictionary with 'documents', 'metadatas', 'distances', 'ids'
        """
        try:
            if top_k is None:
                top_k = settings.top_k_results
            
            # Default threshold if not provided
            if threshold is None:
                threshold = settings.similarity_threshold
            
            # Generate query embedding
            
            # Generate query embedding
            query_embedding = self.embedding_function([query])[0]
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter_dict
            )
            
            # Filter by similarity threshold (convert distance to similarity)
            # ChromaDB uses L2 distance, lower is better
            filtered_results = {
                'documents': [],
                'metadatas': [],
                'distances': [],
                'ids': []
            }
            
            if results['documents'] and results['documents'][0]:
                for i, distance in enumerate(results['distances'][0]):
                    logger.debug(f"Found match: {distance}")
                    # Filter by threshold
                    if distance < threshold:
                        filtered_results['documents'].append(results['documents'][0][i])
                        filtered_results['metadatas'].append(results['metadatas'][0][i])
                        filtered_results['distances'].append(distance)
                        filtered_results['ids'].append(results['ids'][0][i])
            
            logger.info(f"Search found {len(results['documents'][0] if results['documents'] else [])} matches, kept {len(filtered_results['documents'])} after filtering")
            return filtered_results
            
        except Exception as e:
            logger.error(f"Error searching vector store: {str(e)}")
            raise
    
    def get_collection_count(self) -> int:
        """Get total number of documents in collection."""
        return self.collection.count()


# Global vector store instance
vector_store = VectorStore()

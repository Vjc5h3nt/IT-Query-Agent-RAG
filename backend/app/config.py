"""Application configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # AWS Configuration
    aws_region: str = "us-east-1"
    aws_bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    aws_bedrock_embedding_model_id: str = "amazon.titan-embed-text-v1"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "*"]
    
    # Storage Paths (relative to backend directory)
    data_folder: str = "../data"
    storage_folder: str = "../storage"
    chroma_db_path: str = "../storage/chroma_db"
    session_db_path: str = "../storage/sessions.db"
    
    # RAG Configuration
    top_k_results: int = 5
    similarity_threshold: float = 0.7  # Low L2 distance = High similarity
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_memory_messages: int = 5
    cross_encoder_enabled: bool = False
    
    # Advanced Reranking Settings
    rerank_top_k: int = 5
    top_k_stage1: int = 50
    
    # Collection name for ChromaDB
    collection_name: str = "document_chunks"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    def get_absolute_path(self, relative_path: str) -> str:
        """Convert relative path to absolute path from backend directory."""
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.abspath(os.path.join(backend_dir, relative_path))


# Global settings instance
settings = Settings()

# Ensure storage directories exist
os.makedirs(settings.get_absolute_path(settings.data_folder), exist_ok=True)
os.makedirs(settings.get_absolute_path(settings.storage_folder), exist_ok=True)
os.makedirs(settings.get_absolute_path(settings.chroma_db_path), exist_ok=True)

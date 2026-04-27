"""Application configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AWS Configuration
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""
    aws_bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    aws_bedrock_embedding_model_id: str = "amazon.titan-embed-text-v1"

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]

    # Storage Paths (relative to backend directory)
    data_folder: str = "../data"
    storage_folder: str = "../storage"
    chroma_db_path: str = "../storage/chroma_db"
    session_db_path: str = "../storage/sessions.db"

    # RAG Configuration
    top_k_results: int = 5
    similarity_threshold: float = 0.7
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_memory_messages: int = 5
    cross_encoder_enabled: bool = False

    # Advanced Reranking Settings
    rerank_top_k: int = 5
    top_k_stage1: int = 50

    # Collection names for ChromaDB
    collection_name: str = "document_chunks"
    jira_collection_name: str = "jira_tickets"

    # Embedding Configuration
    embedding_dimensions: int = 1536
    embedding_max_workers: int = 15
    embedding_batch_size: int = 500

    # LLM Generation
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # Response cache
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    cache_max_size: int = 500

    # Retry & Throttling
    retry_delays: List[int] = [5, 10, 20]

    # Query Processing
    listing_query_boost: int = 4
    listing_query_max_k: int = 60
    short_query_word_limit: int = 12
    casual_query_word_limit: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
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
# v2

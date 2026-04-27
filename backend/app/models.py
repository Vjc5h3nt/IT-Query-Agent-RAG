"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = Field(None, description="Performance metrics")
    citations: Optional[List[Dict[str, Any]]] = Field(None, description="Retrieved text snippets")


class ResponseMetrics(BaseModel):
    """Performance metrics for a single AI response."""
    latency_s: float = Field(..., description="End-to-end latency in seconds")
    retrieval_s: Optional[float] = Field(None, description="Retrieval time (s)")
    generation_s: Optional[float] = Field(None, description="LLM generation time (s)")
    input_tokens: int = Field(0, description="Prompt tokens")
    output_tokens: int = Field(0, description="Response tokens")
    total_tokens: int = Field(0, description="Total tokens")
    query_type: Optional[str] = Field(None, description="'rag' or 'casual'")
    sources_retrieved: Optional[int] = Field(None, description="Chunks retrieved")


class Citation(BaseModel):
    """A single retrieved text snippet used to build the answer."""
    id: str = Field(..., description="Source ID (ticket ID or filename)")
    label: str = Field(..., description="Human-readable label with metadata")
    snippet: str = Field(..., description="Retrieved text snippet sent to the LLM")
    source_type: str = Field("jira", description="'jira' or 'pdf'")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """Request model for sending a chat message."""
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., min_length=1, description="User message")
    use_knowledge_base: bool = Field(True, description="Whether to use the vector knowledge base")
    use_reranking: bool = Field(False, description="Whether to use Cross-Encoder reranking")
    context_messages: Optional[int] = Field(None, ge=1, le=25, description="Number of conversation turns to include (1-25). Defaults to server setting.")


class RerankResult(BaseModel):
    """Details of a reranked document."""
    initial_rank: int
    final_rank: int
    score: float
    filename: str
    page: Optional[str] = "N/A"


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    session_id: str
    user_message: ChatMessage
    assistant_message: ChatMessage
    sources: List[str] = Field(default_factory=list)
    rerank_summary: Optional[List[RerankResult]] = Field(None)
    metrics: Optional[ResponseMetrics] = Field(None)
    citations: Optional[List[Citation]] = Field(None)


class SessionCreate(BaseModel):
    """Request model for creating a new session."""
    name: Optional[str] = Field(None, description="Optional session name")


class Session(BaseModel):
    """Session model."""
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class SessionDetail(Session):
    """Detailed session model with messages."""
    messages: List[ChatMessage] = Field(default_factory=list)


class IngestionRequest(BaseModel):
    """Request model for document ingestion settings."""
    chunk_size: Optional[int] = Field(None, description="Size of text chunks")
    chunk_overlap: Optional[int] = Field(None, description="Overlap between chunks")
    # For updating application defaults via ingestion trigger
    top_k_stage1: Optional[int] = Field(None, description="Number of candidates for reranking")
    rerank_top_k: Optional[int] = Field(None, description="Final number of results after reranking")
    max_memory_messages: Optional[int] = Field(None, description="Chat memory window size")


class IngestionResponse(BaseModel):
    """Response model for document ingestion."""
    total_files: int
    new_files_processed: int
    skipped_files: int
    total_chunks_created: int
    processed_files: List[str] = Field(default_factory=list)
    skipped_files_list: List[str] = Field(default_factory=list)


class IngestionStatus(BaseModel):
    """Status of ingested documents."""
    filename: str
    file_path: str
    ingestion_date: datetime
    chunk_count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    vector_store_initialized: bool
    database_initialized: bool


class CacheStats(BaseModel):
    """Cache statistics."""
    total_keys: int
    active_keys: int


class MetricsResponse(BaseModel):
    """Runtime metrics response."""
    version: str
    cache: CacheStats
    vector_store: Dict[str, int]

"""FastAPI main application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from app.config import settings
from app.models import HealthResponse
from app.api import chat, sessions, ingestion, jira_ingestion
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Resolve frontend dist path at module level (fixes forward-reference bug)
_frontend_dist = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'dist')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting RAG Chatbot API")
    logger.info(f"Data folder: {settings.get_absolute_path(settings.data_folder)}")
    logger.info(f"Storage folder: {settings.get_absolute_path(settings.storage_folder)}")

    from services.vector_store import vector_store, jira_vector_store

    logger.info(f"PDF vector store  : {vector_store.get_collection_count()} documents  (collection: '{vector_store._collection_name}')")
    logger.info(f"JIRA vector store : {jira_vector_store.get_collection_count()} documents  (collection: '{jira_vector_store._collection_name}')")
    logger.info("Application startup complete")

    yield

    logger.info("Shutting down RAG Chatbot API")


app = FastAPI(
    title="RAG Chatbot API",
    description="RAG-based chatbot with AWS Bedrock, session management, and rolling memory",
    version="3.3.1",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(ingestion.router)
app.include_router(jira_ingestion.router)


@app.get("/", tags=["root"])
async def root():
    """Serves the frontend or API info."""
    if os.path.isdir(_frontend_dist):
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
    return {
        "message": "RAG Chatbot API",
        "version": "3.3.1",
        "docs": "/docs"
    }


@app.get("/settings", tags=["settings"])
async def get_settings():
    """Return current server configuration for the frontend."""
    return {
        "max_memory_messages": settings.max_memory_messages,
        "similarity_threshold": settings.similarity_threshold,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "top_k_results": settings.top_k_results,
        "cross_encoder_enabled": settings.cross_encoder_enabled,
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "embedding_model": settings.aws_bedrock_embedding_model_id,
        "llm_model": settings.aws_bedrock_model_id,
    }


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint."""
    try:
        from services.vector_store import vector_store

        vector_store_ok = vector_store.get_collection_count() >= 0

        return HealthResponse(
            status="healthy",
            vector_store_initialized=vector_store_ok,
            database_initialized=True
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            vector_store_initialized=False,
            database_initialized=False
        )


# Serve built frontend static files if the dist folder exists
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(_frontend_dist, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )

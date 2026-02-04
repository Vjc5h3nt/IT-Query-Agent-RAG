"""FastAPI main application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.models import HealthResponse
from app.api import chat, sessions, ingestion
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting RAG Chatbot API")
    logger.info(f"Data folder: {settings.get_absolute_path(settings.data_folder)}")
    logger.info(f"Storage folder: {settings.get_absolute_path(settings.storage_folder)}")
    
    # Initialize services (they auto-initialize on import)
    from services.vector_store import vector_store
    from database.session_db import session_db
    
    logger.info(f"Vector store initialized with {vector_store.get_collection_count()} documents")
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG Chatbot API")


# Create FastAPI app
app = FastAPI(
    title="RAG Chatbot API",
    description="RAG-based chatbot with AWS Bedrock, session management, and rolling memory",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(ingestion.router)


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "message": "RAG Chatbot API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint."""
    try:
        from services.vector_store import vector_store
        from database.session_db import session_db
        
        vector_store_ok = vector_store.get_collection_count() >= 0
        db_ok = True  # If we get here, DB is working
        
        return HealthResponse(
            status="healthy",
            vector_store_initialized=vector_store_ok,
            database_initialized=db_ok
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return HealthResponse(
            status="unhealthy",
            vector_store_initialized=False,
            database_initialized=False
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )

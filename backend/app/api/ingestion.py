"""Document ingestion API endpoints."""
from fastapi import APIRouter, HTTPException
from typing import List
from app.models import IngestionResponse, IngestionStatus, IngestionRequest
from services.document_processor import document_processor
from services.vector_store import vector_store, jira_vector_store
from database.session_db import session_db
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("", response_model=IngestionResponse)
async def ingest_documents(request: IngestionRequest = None):
    """
    Ingest documents from data folder (incremental).
    Only processes new or modified documents.
    
    Args:
        request: Optional ingestion settings
        
    Returns:
        Ingestion statistics
    """
    try:
        from app.config import settings
        
        # Update app settings if provided
        if request:
            if request.top_k_stage1 is not None:
                settings.top_k_stage1 = request.top_k_stage1
                logger.info(f"Updated top_k_stage1 to {request.top_k_stage1}")
            
            if request.rerank_top_k is not None:
                settings.rerank_top_k = request.rerank_top_k
                # Also update top_k_results so it applies to the generation phase
                settings.top_k_results = request.rerank_top_k
                logger.info(f"Updated rerank_top_k to {request.rerank_top_k}")
            
            if request.max_memory_messages is not None:
                settings.max_memory_messages = request.max_memory_messages
                logger.info(f"Updated max_memory_messages to {request.max_memory_messages}")

        # Get files that need processing
        files_to_process, skipped_files = document_processor.get_files_to_process()
        
        if not files_to_process and not skipped_files:
            return IngestionResponse(
                total_files=0,
                new_files_processed=0,
                skipped_files=0,
                total_chunks_created=0,
                processed_files=[],
                skipped_files_list=[]
            )
        
        total_chunks = 0
        processed_filenames = []
        
        if files_to_process:
            # Process documents with possible overrides
            chunk_size = request.chunk_size if request else None
            chunk_overlap = request.chunk_overlap if request else None
            
            result = document_processor.process_documents(
                files_to_process, 
                chunk_size=chunk_size, 
                chunk_overlap=chunk_overlap
            )
            
            chunks = result['chunks']
            metadatas = result['metadatas']
            file_chunk_counts = result['file_chunk_counts']
            
            if chunks:
                # Generate unique IDs for chunks
                chunk_ids = [str(uuid.uuid4()) for _ in chunks]
                
                # Add to vector store
                vector_store.add_documents(
                    texts=chunks,
                    metadatas=metadatas,
                    ids=chunk_ids
                )
                
                total_chunks = len(chunks)
                logger.info(f"Added {total_chunks} chunks to vector store")
            
            # Update document metadata in database
            for file_path in files_to_process:
                chunk_count = file_chunk_counts.get(
                    document_processor.calculate_file_hash(file_path),
                    0
                )
                from pathlib import Path
                filename = Path(file_path).name
                chunk_count = file_chunk_counts.get(filename, 0)
                
                document_processor.update_document_metadata(file_path, chunk_count)
                processed_filenames.append(filename)
        
        response = IngestionResponse(
            total_files=len(files_to_process) + len(skipped_files),
            new_files_processed=len(files_to_process),
            skipped_files=len(skipped_files),
            total_chunks_created=total_chunks,
            processed_files=processed_filenames,
            skipped_files_list=skipped_files
        )
        
        logger.info(f"Ingestion complete: {len(files_to_process)} processed, {len(skipped_files)} skipped")
        return response
        
    except Exception as e:
        logger.error(f"Error during ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=List[IngestionStatus])
async def get_ingestion_status():
    """
    Get status of all ingested documents.
    
    Returns:
        List of ingested document metadata
    """
    try:
        documents = session_db.get_all_documents()
        
        return [
            IngestionStatus(
                filename=doc.filename,
                file_path=doc.file_path,
                ingestion_date=doc.ingestion_date,
                chunk_count=doc.chunk_count
            )
            for doc in documents
        ]
    except Exception as e:
        logger.error(f"Error getting ingestion status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/vector-store")
async def delete_vector_store():
    """Delete all documents from the PDF/document vector store and clear metadata."""
    try:
        vector_store.reset_collection()
        deleted_count = session_db.delete_all_documents()
        logger.info(f"PDF vector store deleted, cleared {deleted_count} DB metadata records")
        return {
            "status": "success",
            "message": f"PDF document store deleted ({deleted_count} metadata records cleared)",
            "metadata_records_deleted": deleted_count
        }
    except Exception as e:
        logger.error(f"Error deleting PDF vector store: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/jira-vector-store")
async def delete_jira_vector_store():
    """Delete all JIRA ticket vectors from the JIRA-specific collection."""
    try:
        count_before = jira_vector_store.get_collection_count()
        jira_vector_store.reset_collection()
        logger.info(f"JIRA vector store deleted ({count_before} vectors removed)")
        return {
            "status": "success",
            "message": f"JIRA vector store deleted ({count_before} ticket vectors removed)",
            "vectors_deleted": count_before
        }
    except Exception as e:
        logger.error(f"Error deleting JIRA vector store: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vector-stats")
async def get_vector_stats():
    """Return doc counts for both the PDF and JIRA ChromaDB collections."""
    try:
        from services.bm25_store import bm25_store
        bm25_count = bm25_store.count() if bm25_store.is_ready() else 0
    except Exception:
        bm25_count = 0

    return {
        "pdf_collection": {
            "name": vector_store._collection_name,
            "count": vector_store.get_collection_count(),
            "description": "PDF and general document chunks"
        },
        "jira_collection": {
            "name": jira_vector_store._collection_name,
            "count": jira_vector_store.get_collection_count(),
            "description": "JIRA XML ticket vectors (symptom + resolution)"
        },
        "bm25_index": {
            "count": bm25_count,
            "description": "OpenSearch BM25 keyword index (JIRA tickets)"
        }
    }

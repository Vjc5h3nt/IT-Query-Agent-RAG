"""Document ingestion API endpoints."""
from fastapi import APIRouter, HTTPException
from typing import List
from app.models import IngestionResponse, IngestionStatus
from services.document_processor import document_processor
from services.vector_store import vector_store
from database.session_db import session_db
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("", response_model=IngestionResponse)
async def ingest_documents():
    """
    Ingest documents from data folder (incremental).
    Only processes new or modified documents.
    
    Returns:
        Ingestion statistics
    """
    try:
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
            # Process documents
            result = document_processor.process_documents(files_to_process)
            
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

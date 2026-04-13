"""
Interactive JIRA XML ingestion API.
Breaks ingestion into a stateful, multi-step pipeline:
1. Upload -> 2. Extract -> 3. Clean -> 4. Index.
"""
import asyncio
import json
import logging
import os
import shutil
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest/jira", tags=["jira-ingestion"])

TEMP_DIR = os.path.join(settings.get_absolute_path(settings.storage_folder), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)


class SessionResponse(BaseModel):
    session_id: str
    message: str


def _make_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event message."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/upload", response_model=SessionResponse)
async def upload_xml(file: UploadFile = File(...)):
    """Step 1: Upload XML file to a temporary location."""
    if not file.filename.endswith(".xml"):
        raise HTTPException(status_code=400, detail="Only .xml files are supported")

    session_id = str(uuid.uuid4())
    temp_path = os.path.join(TEMP_DIR, f"{session_id}.xml")

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded XML: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    return SessionResponse(session_id=session_id, message="File uploaded successfully")


@router.post("/extract/{session_id}")
async def extract_data(session_id: str):
    """Step 2: Parse XML without HTML cleaning. Save as JSONL and return preview."""
    xml_path = os.path.join(TEMP_DIR, f"{session_id}.xml")
    if not os.path.exists(xml_path):
        raise HTTPException(status_code=404, detail="Session or XML file not found")

    out_path = os.path.join(TEMP_DIR, f"{session_id}_extracted.jsonl")
    from services.jira.jira_xml_ingestor import parse as parse_jira_xml

    preview = []
    count = 0
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            for ticket in parse_jira_xml(xml_path, do_clean_html=False):
                if count < 5:
                    preview.append(ticket)
                f.write(json.dumps(ticket) + "\n")
                count += 1
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    return {"session_id": session_id, "total_extracted": count, "preview": preview}


@router.post("/clean/{session_id}")
async def clean_data(session_id: str):
    """Step 3: Read extracted JSONL, clean HTML, save as JSONL and return preview."""
    in_path = os.path.join(TEMP_DIR, f"{session_id}_extracted.jsonl")
    if not os.path.exists(in_path):
        raise HTTPException(status_code=404, detail="Extracted data not found")

    out_path = os.path.join(TEMP_DIR, f"{session_id}_cleaned.jsonl")
    from services.jira.html_cleaner import clean_html

    preview = []
    count = 0
    try:
        with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
            for line in fin:
                ticket = json.loads(line)
                
                # Apply HTML cleaning
                ticket["summary"] = clean_html(ticket.get("summary", ""))
                ticket["description"] = clean_html(ticket.get("description", ""))
                ticket["resolution"] = clean_html(ticket.get("resolution", ""))
                ticket["resolution_details"] = clean_html(ticket.get("resolution_details", ""))
                
                for comment in ticket.get("comments", []):
                    comment["text"] = clean_html(comment.get("text", ""))

                if count < 5:
                    preview.append(ticket)
                fout.write(json.dumps(ticket) + "\n")
                count += 1
    except Exception as e:
        logger.error(f"Cleaning failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleaning failed: {e}")

    return {"session_id": session_id, "total_cleaned": count, "preview": preview}


@router.get("/download/{session_id}/{phase}")
async def download_data(session_id: str, phase: str):
    """Download intermediate files (phase: 'extracted' or 'cleaned')."""
    if phase not in ["extracted", "cleaned"]:
        raise HTTPException(status_code=400, detail="Invalid phase")
        
    file_path = os.path.join(TEMP_DIR, f"{session_id}_{phase}.jsonl")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(
        path=file_path,
        filename=f"jira_{phase}.jsonl",
        media_type="application/jsonlines"
    )


@router.post("/index/{session_id}")
async def index_data(session_id: str, background_tasks: BackgroundTasks, batch_size: int = 100):
    """Step 4: Index the cleaned JSONL into ChromaDB and OpenSearch."""
    cleaned_path = os.path.join(TEMP_DIR, f"{session_id}_cleaned.jsonl")
    if not os.path.exists(cleaned_path):
        raise HTTPException(status_code=404, detail="Cleaned data not found")

    return StreamingResponse(
        _run_indexing_streaming(session_id, cleaned_path, batch_size, background_tasks),
        media_type="text/event-stream",
    )


async def _run_indexing_streaming(session_id: str, jsonl_path: str, batch_size: int, bg_tasks: BackgroundTasks) -> AsyncGenerator[str, None]:
    """Stream indexing progress."""
    from services.jira.vector_preparer import prepare_vectors
    from services.vector_store import jira_vector_store as vector_store
    from services.bm25_store import bm25_store
    from services.embedding_helpers import embed_with_retry, normalize_embeddings
    from database.session_db import session_db

    stats = {
        "job_id": session_id,
        "status": "running",
        "tickets_parsed": 0,
        "vectors_created": 0,
        "deduplicated": 0,
        "failed_batches": 0,
        "current_batch": 0,
        "error": None,
    }

    yield _make_event("start", {"job_id": session_id, "message": "Indexing started"})
    await asyncio.sleep(0)

    batch_vectors = []
    raw_ticket_batch = []
    batch_num = 0

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                
                ticket = json.loads(line)
                stats["tickets_parsed"] += 1

                try:
                    vectors = prepare_vectors(ticket)
                    batch_vectors.extend(vectors)
                    raw_ticket_batch.append(ticket)
                except Exception as e:
                    logger.error(f"Vector prep failed for {ticket.get('ticket_id')}: {e}")

                if len(batch_vectors) >= batch_size:
                    batch_num += 1
                    stats["current_batch"] = batch_num
                    batch_ids = [v["id"] for v in batch_vectors]

                    try:
                        # Dense
                        existing = vector_store.get_existing_ids(batch_ids)
                        new_batch = [v for v in batch_vectors if v["id"] not in existing]
                        dedup = len(batch_vectors) - len(new_batch)
                        stats["deduplicated"] += dedup

                        if new_batch:
                            embeddings = await asyncio.get_event_loop().run_in_executor(
                                None, embed_with_retry, [v["text"] for v in new_batch]
                            )
                            embeddings = normalize_embeddings(embeddings)
                            vector_store.collection.add(
                                ids=[v["id"] for v in new_batch],
                                documents=[v["text"] for v in new_batch],
                                embeddings=embeddings,
                                metadatas=[v["metadata"] for v in new_batch],
                            )
                            stats["vectors_created"] += len(new_batch)

                        # Sparse (BM25)
                        if bm25_store.is_ready() or bm25_store._client is not None:
                            bm25_store.add_tickets(raw_ticket_batch)
                        else:
                            # if not ready yet but client is none, ensure it tries to connect
                            bm25_store._ensure_index()
                            bm25_store.add_tickets(raw_ticket_batch)

                    except Exception as e:
                        logger.error(f"Batch {batch_num} failed: {e}")
                        stats["failed_batches"] += 1

                    yield _make_event("progress", stats)
                    await asyncio.sleep(0)
                    
                    batch_vectors.clear()
                    raw_ticket_batch.clear()

        # Final batch
        if batch_vectors:
            batch_num += 1
            stats["current_batch"] = batch_num
            batch_ids = [v["id"] for v in batch_vectors]

            try:
                existing = vector_store.get_existing_ids(batch_ids)
                new_batch = [v for v in batch_vectors if v["id"] not in existing]
                stats["deduplicated"] += len(batch_vectors) - len(new_batch)

                if new_batch:
                    embeddings = await asyncio.get_event_loop().run_in_executor(
                        None, embed_with_retry, [v["text"] for v in new_batch]
                    )
                    embeddings = normalize_embeddings(embeddings)
                    vector_store.collection.add(
                        ids=[v["id"] for v in new_batch],
                        documents=[v["text"] for v in new_batch],
                        embeddings=embeddings,
                        metadatas=[v["metadata"] for v in new_batch],
                    )
                    stats["vectors_created"] += len(new_batch)

                if bm25_store.is_ready() or bm25_store._client is not None:
                    bm25_store.add_tickets(raw_ticket_batch)

            except Exception as e:
                logger.error(f"Final batch failed: {e}")
                stats["failed_batches"] += 1

        stats["status"] = "complete"
        stats["total_chroma_count"] = vector_store.collection.count()
        
        # OpenSearch auto-persists so no need to save()
        # Save session
        session_db.add_document_metadata(
            filename=f"jira_export_{session_id[:8]}.xml",
            file_hash=session_id,  # using session_id as a unique hash
            file_path="jira_export",
            chunk_count=stats["vectors_created"]
        )

        yield _make_event("progress", stats)
        
        # Cleanup files in background
        def cleanup_temp_files():
            paths = [
                os.path.join(TEMP_DIR, f"{session_id}.xml"),
                os.path.join(TEMP_DIR, f"{session_id}_extracted.jsonl"),
                os.path.join(TEMP_DIR, f"{session_id}_cleaned.jsonl")
            ]
            for p in paths:
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {p}: {e}")
                    
        bg_tasks.add_task(cleanup_temp_files)

    except Exception as e:
        logger.error(f"Ingestion job {session_id} failed: {e}", exc_info=True)
        stats["status"] = "error"
        stats["error"] = str(e)
        yield _make_event("progress", stats)

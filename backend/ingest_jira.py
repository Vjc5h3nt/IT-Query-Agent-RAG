#!/usr/bin/env python3
"""
JIRA XML ingestion CLI.

Usage:
    python ingest_jira.py --xml path/to/export.xml --batch-size 100

Pipeline:
    XML (streaming) → clean/normalize → multi-vector → 8K cap
    → dedup gate → embed (batch) → normalize → Chroma insert → log
"""
import argparse
import logging
import sys
import time
import os
from typing import List, Dict, Any

# Ensure backend/ is in the Python path when running as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.jira.jira_xml_ingestor import parse as parse_jira_xml
from services.jira.vector_preparer import prepare_vectors
from services.vector_store import vector_store
from services.bedrock_client import bedrock_client
from database.session_db import session_db

import numpy as np
from tqdm import tqdm

# ── Logging setup ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest_jira")

# ── Retry settings for Bedrock throttling ─────────────────────────────
_RETRY_DELAYS = [5, 10, 20]  # exponential backoff seconds


def _embed_with_retry(texts: List[str]) -> List[List[float]]:
    """
    Call Bedrock embeddings with exponential backoff on ThrottlingException.
    Retries up to 3 times (5s → 10s → 20s), then raises.
    """
    last_error = None
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        try:
            return bedrock_client.generate_embeddings(texts)
        except Exception as e:
            if "ThrottlingException" in str(e) or "throttling" in str(e).lower():
                logger.warning(
                    f"Bedrock throttle on attempt {attempt}, sleeping {delay}s",
                    extra={"attempt": attempt, "delay_s": delay},
                )
                time.sleep(delay)
                last_error = e
            else:
                raise  # Non-throttle errors bubble up immediately
    raise last_error  # type: ignore


def _normalize_embeddings(embeddings: List[List[float]]) -> List[List[float]]:
    """L2-normalize a list of embedding vectors."""
    normalized = []
    for emb in embeddings:
        arr = np.array(emb, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        normalized.append(arr.tolist())
    return normalized


def ingest(xml_path: str, batch_size: int = 100) -> None:
    """
    Run the full JIRA ingestion pipeline.

    Args:
        xml_path:   Absolute path to the JIRA XML export.
        batch_size: Number of vector entries to embed and insert per batch.
    """
    if not os.path.isfile(xml_path):
        logger.error(f"XML file not found: {xml_path}")
        sys.exit(1)

    logger.info(f"Starting JIRA ingestion: {xml_path} (batch_size={batch_size})")

    total_tickets = 0
    total_vectors_created = 0
    total_deduplicated = 0
    total_failed_batches = 0

    batch_vectors: List[Dict[str, Any]] = []

    def flush_batch(batch: List[Dict[str, Any]]) -> None:
        """Embed, normalize, dedup-check, and insert a batch of vectors."""
        nonlocal total_vectors_created, total_deduplicated, total_failed_batches

        if not batch:
            return

        batch_ids = [v["id"] for v in batch]
        batch_start_label = batch_ids[0]

        try:
            # 1. Deduplication gate — skip already-indexed IDs
            existing_ids = vector_store.get_existing_ids(batch_ids)
            new_batch = [v for v in batch if v["id"] not in existing_ids]
            skipped = len(batch) - len(new_batch)
            total_deduplicated += skipped

            if skipped > 0:
                logger.debug(
                    f"Deduplicated {skipped} already-indexed vectors",
                    extra={"batch_start": batch_start_label, "skipped": skipped},
                )

            if not new_batch:
                return

            # 2. Embed with retry
            texts = [v["text"] for v in new_batch]
            embeddings = _embed_with_retry(texts)

            # 3. L2 normalize
            embeddings = _normalize_embeddings(embeddings)

            # 4. Insert into Chroma
            vector_store.collection.add(
                ids=[v["id"] for v in new_batch],
                documents=texts,
                embeddings=embeddings,
                metadatas=[v["metadata"] for v in new_batch],
            )

            total_vectors_created += len(new_batch)
            logger.info(
                "Batch indexed",
                extra={
                    "batch_start": batch_start_label,
                    "count": len(new_batch),
                    "skipped_dedup": skipped,
                },
            )

        except Exception as e:
            total_failed_batches += 1
            logger.error(
                "Batch failed — skipping",
                extra={"batch_start": batch_start_label, "error": str(e)},
            )

    # ── Main streaming loop ────────────────────────────────────────────
    with tqdm(desc="Indexing JIRA tickets", unit="ticket") as pbar:
        for ticket in parse_jira_xml(xml_path):
            total_tickets += 1

            try:
                vectors = prepare_vectors(ticket)
                batch_vectors.extend(vectors)
            except Exception as e:
                logger.error(
                    "Vector preparation failed for ticket",
                    extra={"ticket_id": ticket.get("ticket_id", "?"), "error": str(e)},
                )

            # Flush when batch is full
            if len(batch_vectors) >= batch_size:
                flush_batch(batch_vectors)
                batch_vectors = []

            pbar.update(1)

    # Flush any remaining vectors
    if batch_vectors:
        flush_batch(batch_vectors)

    # ── Record ingestion in session DB ─────────────────────────────────
    try:
        import hashlib
        xml_hash = hashlib.md5(xml_path.encode()).hexdigest()
        session_db.add_document_metadata(
            filename=os.path.basename(xml_path),
            file_hash=xml_hash,
            file_path=xml_path,
            chunk_count=total_vectors_created,
        )
    except Exception as e:
        logger.warning(f"Could not save ingestion metadata to session_db: {e}")

    # ── Summary ────────────────────────────────────────────────────────
    logger.info(
        "Ingestion complete",
        extra={
            "total_tickets_parsed": total_tickets,
            "total_vectors_created": total_vectors_created,
            "total_deduplicated": total_deduplicated,
            "failed_batches": total_failed_batches,
            "final_chroma_count": vector_store.get_collection_count(),
        },
    )
    print(
        f"\n✅ Done! Tickets: {total_tickets} | "
        f"Vectors indexed: {total_vectors_created} | "
        f"Deduplicated: {total_deduplicated} | "
        f"Failed batches: {total_failed_batches} | "
        f"Chroma total: {vector_store.get_collection_count()}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest JIRA XML export into the ChromaDB vector store.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--xml",
        required=True,
        help="Path to the JIRA XML export file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of vector entries to embed and insert per batch.",
    )
    args = parser.parse_args()
    ingest(xml_path=os.path.abspath(args.xml), batch_size=args.batch_size)


if __name__ == "__main__":
    main()

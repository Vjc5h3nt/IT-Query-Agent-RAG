"""Shared embedding utilities — retry logic and L2 normalization.

Eliminates duplication across ingest_jira.py, api/jira_ingestion.py, and vector_store.py.
"""
import logging
import time
from typing import List

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def embed_with_retry(texts: List[str]) -> List[List[float]]:
    """Call Bedrock embeddings with exponential backoff on ThrottlingException.

    Uses settings.retry_delays for backoff schedule (default [5, 10, 20]s).
    Non-throttle errors are raised immediately.
    """
    from services.bedrock_client import bedrock_client

    last_error = None
    for attempt, delay in enumerate(settings.retry_delays, start=1):
        try:
            return bedrock_client.generate_embeddings(texts)
        except Exception as e:
            error_str = str(e).lower()
            if "throttling" in error_str:
                logger.warning(f"Bedrock throttle on attempt {attempt}, sleeping {delay}s")
                time.sleep(delay)
                last_error = e
            else:
                raise
    raise last_error  # type: ignore[misc]


def normalize_embeddings(embeddings: List[List[float]]) -> List[List[float]]:
    """L2-normalize a list of embedding vectors."""
    normalized = []
    for emb in embeddings:
        arr = np.array(emb, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        normalized.append(arr.tolist())
    return normalized

"""
Multi-vector preparation for JIRA tickets.

Creates two embedding entries per ticket:
  - symptom: summary + description + first 3 comments
  - resolution: resolution_details + last 2 comments

Enforces a hard 8,000 character cap before embedding to prevent
Titan token overflow. Skips entries with < 15 meaningful characters.
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Noise thresholds
_MIN_TEXT_LENGTH = 15
_MAX_TEXT_LENGTH = 8000


def _assemble_text(*parts: str) -> str:
    """Join non-empty text parts, strip result."""
    return "\n".join(p.strip() for p in parts if p and p.strip())


def _truncate(text: str) -> str:
    """Hard cap at 8000 characters before embedding."""
    if len(text) > _MAX_TEXT_LENGTH:
        logger.debug(f"Truncating vector text from {len(text)} → {_MAX_TEXT_LENGTH} chars")
        return text[:_MAX_TEXT_LENGTH]
    return text


def prepare_vectors(ticket: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create up to 2 vector entries for a single JIRA ticket.

    IDs are deterministic: ``<ticket_id>::<vector_type>``
    This prevents re-indexing on pipeline re-runs. Known limitation:
    if ticket content changes after indexing, these IDs will collide
    and the old vector will NOT be replaced — requires manual purge.

    Args:
        ticket: Normalized ticket dict from jira_xml_ingestor.parse().

    Returns:
        List of 0–2 vector entry dicts ready for ChromaDB insertion.
    """
    ticket_id = ticket.get("ticket_id", "")
    if not ticket_id:
        logger.warning("Ticket has no ticket_id, skipping vector preparation")
        return []

    # Shared metadata
    created_date = ticket.get("created", "")
    metadata = {
        "ticket_id":          ticket_id,
        "priority":           ticket.get("priority", ""),
        "city":               ticket.get("city", ""),
        "hcl_team":           ticket.get("hcl_team", ""),
        "impact":             ticket.get("impact", ""),
        "ticket_transferred": ticket.get("ticket_transferred", ""),
        "status":             ticket.get("status", ""),
        "created":            created_date,
        "vector_type":        "",  # set below per entry
    }

    comments: List[Dict[str, str]] = ticket.get("comments", [])
    comment_texts = [c.get("text", "") for c in comments if c.get("text")]

    vectors: List[Dict[str, Any]] = []
    
    # Prefix to inject explicit Date context into the LLM's chunk
    date_prefix = f"[Created: {created_date}]" if created_date else "[Created: Unknown]"

    # ── 1. Symptom Vector ──────────────────────────────────────────────
    first_3_comments = comment_texts[:3]
    symptom_text = _assemble_text(
        date_prefix,
        ticket.get("summary", ""),
        ticket.get("description", ""),
        *first_3_comments,
    )
    symptom_text = _truncate(symptom_text)

    if len(symptom_text) >= _MIN_TEXT_LENGTH:
        sym_meta = {**metadata, "vector_type": "symptom"}
        vectors.append({
            "id":          f"{ticket_id}::symptom",
            "ticket_id":   ticket_id,
            "vector_type": "symptom",
            "text":        symptom_text,
            "metadata":    sym_meta,
        })
    else:
        logger.debug(f"Skipping symptom vector for {ticket_id}: text too short ({len(symptom_text)} chars)")

    # ── 2. Resolution Vector ───────────────────────────────────────────
    last_2_comments = comment_texts[-2:] if len(comment_texts) >= 2 else comment_texts
    resolution_text = _assemble_text(
        date_prefix,
        ticket.get("resolution_details", ""),
        ticket.get("resolution", ""),
        *last_2_comments,
    )
    resolution_text = _truncate(resolution_text)

    if len(resolution_text) >= _MIN_TEXT_LENGTH:
        res_meta = {**metadata, "vector_type": "resolution"}
        vectors.append({
            "id":          f"{ticket_id}::resolution",
            "ticket_id":   ticket_id,
            "vector_type": "resolution",
            "text":        resolution_text,
            "metadata":    res_meta,
        })
    else:
        logger.debug(f"Skipping resolution vector for {ticket_id}: text too short ({len(resolution_text)} chars)")

    return vectors

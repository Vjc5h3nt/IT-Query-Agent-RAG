"""
Pre-retrieval query metadata extractor.

Extracts structured metadata filters from a natural language query
to enable pre-filtering in ChromaDB before vector similarity search.

Returns a ChromaDB-compatible filter dict using $and/$eq syntax.
Returns {} if no metadata is detected — caller must check before passing.
"""
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# ── Device model patterns ─────────────────────────────────────────────
_DEVICE_PATTERNS = [
    re.compile(r"\b(zebra)\b", re.IGNORECASE),
    re.compile(r"\b(MC\d{2,6})\b", re.IGNORECASE),
    re.compile(r"\b(TC\d{2,6})\b", re.IGNORECASE),
    re.compile(r"\b(WT\d{2,6})\b", re.IGNORECASE),
    re.compile(r"\b(DS\d{2,6})\b", re.IGNORECASE),
    re.compile(r"\b(iphone|ipad|android)\b", re.IGNORECASE),
]

# ── Error code patterns ───────────────────────────────────────────────
_ERROR_CODE_PATTERNS = [
    re.compile(r"\b(ORA-\d{4,6})\b", re.IGNORECASE),
    re.compile(r"\b(HTTP\s?\d{3})\b", re.IGNORECASE),
    re.compile(r"\b(ERR[_-]?\d{3,6})\b", re.IGNORECASE),
    re.compile(r"\b(ERROR\s\d{3,6})\b", re.IGNORECASE),
    re.compile(r"\b(\d{3,6}-\d{3,6})\b"),  # generic code pattern like 503-001
]

# ── Priority / severity keywords ─────────────────────────────────────
_PRIORITY_MAP = {
    "critical":  "critical",
    "sev-1":     "critical",
    "sev 1":     "critical",
    "p1":        "high",
    "high":      "high",
    "medium":    "medium",
    "p2":        "medium",
    "low":       "low",
    "p3":        "low",
}
_PRIORITY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _PRIORITY_MAP.keys()) + r")\b",
    re.IGNORECASE
)

# ── City name lookup set (lowercase) ────────────────────────────────
# Extend this list with cities from your actual JIRA dataset.
_KNOWN_CITIES = {
    "london", "new york", "chicago", "los angeles", "toronto", "paris",
    "berlin", "sydney", "singapore", "mumbai", "bangalore", "hyderabad",
    "chennai", "delhi", "dubai", "amsterdam", "tokyo", "seoul",
    "hong kong", "jakarta", "kuala lumpur", "manila", "bangkok",
    "buenos aires", "sao paulo", "mexico city", "johannesburg",
}


def _build_chroma_filter(conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build ChromaDB-compatible filter from a list of {field: {$eq: val}} dicts."""
    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def extract_query_metadata(query: str) -> Dict[str, Any]:
    """
    Extract structured metadata filters from a natural language query.

    Detects: device models, error codes, city names, and priority keywords.
    All matched values are lowercased for consistency with indexed metadata.

    Returns:
        ChromaDB filter dict, e.g.:
        {
            "$and": [
                {"city": {"$eq": "london"}},
                {"priority": {"$eq": "high"}}
            ]
        }
        Returns {} if nothing is detected — caller must check before use.
    """
    if not query or not query.strip():
        return {}

    try:
        conditions: List[Dict[str, Any]] = []
        query_lower = query.lower()

        # 1. City detection
        for city in _KNOWN_CITIES:
            if city in query_lower:
                conditions.append({"city": {"$eq": city}})
                logger.debug(f"Detected city filter: {city}")
                break  # Only filter by one city at a time

        # 2. Priority detection
        priority_match = _PRIORITY_PATTERN.search(query)
        if priority_match:
            keyword = priority_match.group(1).lower()
            normalized = _PRIORITY_MAP.get(keyword, keyword)
            conditions.append({"priority": {"$eq": normalized}})
            logger.debug(f"Detected priority filter: {normalized}")

        # Note: Device models and error codes are extracted for logging/context
        # but not used as ChromaDB filters (they are not stored as metadata fields).
        # Extend metadata schema and add filter conditions here if needed.
        for pattern in _DEVICE_PATTERNS:
            m = pattern.search(query)
            if m:
                logger.debug(f"Detected device mention in query: {m.group(1)}")
                break

        for pattern in _ERROR_CODE_PATTERNS:
            m = pattern.search(query)
            if m:
                logger.debug(f"Detected error code in query: {m.group(1)}")
                break

        result = _build_chroma_filter(conditions)
        if result:
            logger.info("Pre-retrieval metadata filter extracted", extra={"filter": str(result)})
        return result

    except Exception as e:
        logger.warning(f"Metadata extraction failed silently: {e}")
        return {}

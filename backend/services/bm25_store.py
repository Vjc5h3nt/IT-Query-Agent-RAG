"""
OpenSearch-backed sparse BM25 retrieval store.

Replaces the in-memory rank_bm25 implementation with a production-grade
OpenSearch index. Same public interface — zero changes needed in
hybrid_retriever.py or rag_engine.py.

Key design decisions:
- Custom `it_analyzer` disables stopwords so error codes like ORA-12541,
  IP addresses, and ticket IDs are never token-destroyed.
- Keyword fields for all metadata (city, priority, hcl_team, etc.) to
  enable exact `term` filter matching.
- Graceful degradation: if OpenSearch is unavailable, is_ready() returns
  False and the caller falls back to dense-only retrieval.
- Upsert by ticket_id for idempotent re-ingestion.
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Index definition ──────────────────────────────────────────────────────────
_INDEX_BODY = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "it_analyzer": {
                    "type": "standard",
                    "stopwords": "_none_",  # preserve ORA-12541, IP addrs, etc.
                }
            }
        },
    },
    "mappings": {
        "properties": {
            # Exact-match fields (never tokenized)
            "ticket_id":         {"type": "keyword"},
            "city":              {"type": "keyword"},
            "priority":          {"type": "keyword"},
            "hcl_team":          {"type": "keyword"},
            "impact":            {"type": "keyword"},
            "status":            {"type": "keyword"},
            "ticket_transferred":{"type": "keyword"},
            # Creation date stored as keyword for exact & BM25 matching
            "created":           {"type": "keyword"},
            # Full-text search field using custom IT analyzer
            "search_text": {
                "type":     "text",
                "analyzer": "it_analyzer",
            },
        }
    },
}


def _get_client():
    """
    Lazy-initialise the OpenSearch client.
    Returns None if the library is not installed or the host is unreachable.
    """
    try:
        from opensearchpy import OpenSearch
        url = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
        client = OpenSearch(
            hosts=[url],
            http_compress=True,
            use_ssl=False,
            verify_certs=False,
            ssl_show_warn=False,
            timeout=10,
            retry_on_timeout=True,
            max_retries=3,
        )
        # Lightweight ping to verify connectivity
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"OpenSearch unavailable: {e} — dense-only fallback active")
        return None


def _flatten_text(ticket: Dict[str, Any]) -> str:
    """Flatten all searchable ticket fields into a single string for BM25."""
    tid = ticket.get("ticket_id", "")
    created = ticket.get("created", "")
    parts = [
        # Ticket ID first so direct ID queries always match
        f"Ticket ID: {tid}" if tid else "",
        f"Created: {created}" if created else "",
        ticket.get("summary", ""),
        ticket.get("description", ""),
        ticket.get("resolution_details", ""),
        ticket.get("resolution", ""),
    ]
    for comment in ticket.get("comments", []):
        parts.append(comment.get("text", "") if isinstance(comment, dict) else str(comment))
    return " ".join(p for p in parts if p)


class BM25Store:
    """
    OpenSearch-backed BM25 sparse retrieval store.

    Public interface (identical to the rank_bm25 version):
        add_tickets(tickets)  → int (new tickets indexed)
        search(query, top_k, filter_dict) → List[dict]
        is_ready() → bool
        count() → int
        reset() → None
        save() → None (no-op; OpenSearch persists automatically)
    """

    def __init__(self):
        self._index = os.getenv("OPENSEARCH_INDEX", "jira_tickets")
        self._client = None     # lazy — created on first use
        self._ready = None      # None = not checked yet
        self._ensure_index()

    # ── Internal helpers ──────────────────────────────────────────────

    def _connect(self):
        if self._client is None:
            self._client = _get_client()
        return self._client

    def _ensure_index(self) -> None:
        """Create the index with proper mapping if it doesn't exist."""
        client = self._connect()
        if client is None:
            self._ready = False
            return
        try:
            if not client.indices.exists(index=self._index):
                client.indices.create(index=self._index, body=_INDEX_BODY)
                logger.info(f"Created OpenSearch index: {self._index}")
            else:
                logger.info(f"OpenSearch index already exists: {self._index}")
            self._ready = True
        except Exception as e:
            logger.error(f"Failed to ensure OpenSearch index: {e}")
            self._ready = False

    # ── Public interface ──────────────────────────────────────────────

    def is_ready(self) -> bool:
        """True when OpenSearch is reachable, index exists, and has at least one document."""
        if self._ready is None:
            self._ensure_index()
        if not self._ready:
            return False
        try:
            client = self._connect()
            if client is None:
                return False
            # Check index exists first (fast)
            if not client.indices.exists(index=self._index):
                return False
            # Then check document count
            return self.count() > 0
        except Exception:
            return False

    def count(self) -> int:
        """Return number of indexed tickets."""
        client = self._connect()
        if client is None:
            return 0
        try:
            result = client.count(index=self._index)
            return result.get("count", 0)
        except Exception as e:
            logger.warning(f"OpenSearch count failed: {e}")
            return 0

    def add_tickets(self, tickets: List[Dict[str, Any]]) -> int:
        """
        Bulk-upsert tickets into OpenSearch. Idempotent — safe to call
        multiple times with overlapping data.

        Returns:
            Number of new tickets successfully indexed.
        """
        client = self._connect()
        if client is None:
            return 0

        try:
            from opensearchpy.helpers import bulk

            actions = []
            for ticket in tickets:
                tid = ticket.get("ticket_id", "")
                if not tid:
                    continue
                text = _flatten_text(ticket)
                if not text.strip():
                    continue

                actions.append({
                    "_op_type":  "index",   # upsert semantics
                    "_index":    self._index,
                    "_id":       tid,       # ticket_id is the doc id → idempotent
                    "_source": {
                        "ticket_id":          tid,
                        "search_text":        text,
                        "created":            ticket.get("created", ""),
                        "city":               ticket.get("city", ""),
                        "priority":           ticket.get("priority", ""),
                        "hcl_team":           ticket.get("hcl_team", ""),
                        "impact":             ticket.get("impact", ""),
                        "status":             ticket.get("status", ""),
                        "ticket_transferred": ticket.get("ticket_transferred", ""),
                    },
                })

            if not actions:
                return 0

            success, errors = bulk(client, actions, raise_on_error=False, stats_only=False)
            if errors:
                logger.warning(f"OpenSearch bulk errors ({len(errors)}): {errors[:3]}")
            logger.info(f"OpenSearch indexed {success}/{len(actions)} tickets")
            return success

        except Exception as e:
            logger.error(f"OpenSearch add_tickets failed: {e}")
            return 0

    def search(
        self,
        query: str,
        top_k: int = 50,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        BM25 search with optional metadata pre-filtering.

        Uses a bool query with:
          - `must` → match on search_text (operator: or for recall)
          - `filter` → exact term matches on keyword fields

        Args:
            query:       Natural-language or keyword query string.
            top_k:       Maximum results to return.
            filter_dict: ChromaDB-style filter dict ($eq/$and/$or).
                         Converted to OpenSearch term/bool filters.

        Returns:
            List of result dicts: {ticket_id, text, score, metadata, rank}.
        """
        client = self._connect()
        if client is None or not query.strip():
            return []

        # Build filter clauses from ChromaDB-style filter_dict
        filter_clauses = _build_os_filters(filter_dict) if filter_dict else []

        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "search_text": {
                                    "query":    query,
                                    "operator": "or",   # high recall; reranker handles precision
                                }
                            }
                        }
                    ],
                    **({"filter": filter_clauses} if filter_clauses else {}),
                }
            },
            "_source": ["ticket_id", "city", "priority", "hcl_team",
                        "impact", "status", "ticket_transferred", "created", "search_text"],
        }

        try:
            response = client.search(index=self._index, body=body)
            hits = response.get("hits", {}).get("hits", [])
            results = []
            for rank, hit in enumerate(hits):
                src = hit["_source"]
                results.append({
                    "ticket_id": src.get("ticket_id", hit["_id"]),
                    "text":      src.get("search_text", ""),
                    "score":     float(hit.get("_score", 0.0)),
                    "metadata": {
                        "ticket_id":          src.get("ticket_id", ""),
                        "created":            src.get("created", ""),
                        "city":               src.get("city", ""),
                        "priority":           src.get("priority", ""),
                        "hcl_team":           src.get("hcl_team", ""),
                        "impact":             src.get("impact", ""),
                        "status":             src.get("status", ""),
                        "ticket_transferred": src.get("ticket_transferred", ""),
                    },
                    "rank": rank,
                })
            logger.debug(f"OpenSearch returned {len(results)} hits for: {query[:60]}")
            return results
        except Exception as e:
            logger.error(f"OpenSearch search failed: {e}")
            return []

    def reset(self) -> None:
        """Delete and recreate the OpenSearch index (wipes all data)."""
        client = self._connect()
        if client is None:
            return
        try:
            if client.indices.exists(index=self._index):
                client.indices.delete(index=self._index)
                logger.info(f"Deleted OpenSearch index: {self._index}")
            client.indices.create(index=self._index, body=_INDEX_BODY)
            logger.info(f"Recreated OpenSearch index: {self._index}")
        except Exception as e:
            logger.error(f"Failed to reset OpenSearch index: {e}")

    def save(self) -> None:
        """
        No-op. OpenSearch persists to disk automatically.
        Kept for interface compatibility with the rank_bm25 version.
        """
        pass


# ── Filter translation ─────────────────────────────────────────────────────────

def _build_os_filters(filter_dict: Dict[str, Any]) -> List[Dict]:
    """
    Translate a ChromaDB-style filter dict to an OpenSearch filter clause list.

    Supports: $eq, $ne, $and, $or.

    Examples:
        {"city": {"$eq": "london"}}
            → [{"term": {"city": "london"}}]

        {"$and": [{"city": {"$eq": "london"}}, {"priority": {"$eq": "critical"}}]}
            → [{"bool": {"must": [{"term": {"city": "london"}},
                                  {"term": {"priority": "critical"}}]}}]
    """
    if not filter_dict:
        return []

    if "$and" in filter_dict:
        sub = []
        for cond in filter_dict["$and"]:
            sub.extend(_build_os_filters(cond))
        return [{"bool": {"must": sub}}] if sub else []

    if "$or" in filter_dict:
        sub = []
        for cond in filter_dict["$or"]:
            sub.extend(_build_os_filters(cond))
        return [{"bool": {"should": sub, "minimum_should_match": 1}}] if sub else []

    clauses = []
    for field, condition in filter_dict.items():
        if field.startswith("$"):
            continue
        if isinstance(condition, dict):
            if "$eq" in condition:
                clauses.append({"term": {field: condition["$eq"]}})
            elif "$ne" in condition:
                clauses.append({"bool": {"must_not": [{"term": {field: condition["$ne"]}}]}})
        else:
            clauses.append({"term": {field: condition}})
    return clauses


# Global singleton — initialised once at startup
bm25_store = BM25Store()

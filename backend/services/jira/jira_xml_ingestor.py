"""
Streaming JIRA XML parser for large exports (100K+ tickets).

Uses lxml.etree.iterparse for event-based streaming — never loads
the entire XML document into memory. Clears elements AND removes
previous siblings after processing to prevent RAM accumulation.
"""
import hashlib
import logging
from typing import Iterator, Dict, Any, List

logger = logging.getLogger(__name__)

# Fields we care about from <customfieldname> matching
_CUSTOM_FIELD_MAP = {
    "city":                  "city",
    "hcl team's":            "hcl_team",
    "impact":                "impact",
    "incident noticed at":   "incident_noticed_at",
    "no.of users affected":  "users_affected",
    "reported source":       "reported_source",
    "resolution details":    "resolution_details",
    "cat pays":              "cat_pays",
    "ticket transferred":    "ticket_transferred",
}

# Fields to completely ignore (SLA, Rank, Dev, scripted, etc.)
_IGNORE_CUSTOM_FIELDS = {
    "rank", "story points", "epic link", "sprint", "watchers", "voters",
    "development", "flagged", "labels", "sla", "time to first response",
    "time to resolution", "time to close after resolution",
    "satisfaction", "request type", "request participants",
    "organisations", "approvals", "customer's pincode",
}


def _safe_text(element, default: str = "") -> str:
    """Return text of an lxml element, or default if None/absent."""
    if element is None:
        return default
    return (element.text or "").strip()


def _extract_custom_fields(item_element) -> Dict[str, str]:
    """Extract recognized custom fields from a JIRA <item> element."""
    custom_data: Dict[str, str] = {}
    customfields = item_element.find("customfields")
    if customfields is None:
        return custom_data

    for cf in customfields.findall("customfield"):
        name_el = cf.find("customfieldname")
        if name_el is None:
            continue
        field_name = (name_el.text or "").strip().lower()

        # Skip ignored fields
        if field_name in _IGNORE_CUSTOM_FIELDS:
            continue

        mapped_key = _CUSTOM_FIELD_MAP.get(field_name)
        if mapped_key is None:
            continue

        # Try to find value inside customfieldvalues/customfieldvalue
        value_el = cf.find("customfieldvalues/customfieldvalue")
        if value_el is not None and value_el.text:
            custom_data[mapped_key] = value_el.text.strip()

    return custom_data


def _extract_comments(item_element, do_clean_html: bool = True) -> List[Dict[str, str]]:
    """
    Extract comments preserving author, created timestamp, and clean text.
    Deduplicates by (author + text_hash) to handle JIRA export duplicates.
    """
    from services.jira.html_cleaner import clean_html

    comments = []
    seen_hashes = set()
    comments_block = item_element.find("comments")
    if comments_block is None:
        return comments

    for comment in comments_block.findall("comment"):
        author = comment.get("author", "").strip()
        created = comment.get("created", "").strip()
        raw_text = comment.text or ""
        
        final_text = clean_html(raw_text) if do_clean_html else raw_text

        if not final_text.strip():
            continue

        # Dedup by author + text content hash
        dedup_key = hashlib.md5(f"{author}{final_text}".encode()).hexdigest()
        if dedup_key in seen_hashes:
            logger.debug(f"Skipping duplicate comment from {author}")
            continue
        seen_hashes.add(dedup_key)

        comments.append({
            "author": author,
            "timestamp": created,
            "text": final_text,
        })

    return comments


def _normalize_metadata(value: str) -> str:
    """Lowercase and strip metadata values for consistent ChromaDB filtering."""
    return (value or "").strip().lower()


def parse(xml_path: str, do_clean_html: bool = True) -> Iterator[Dict[str, Any]]:
    """
    Stream-parse a JIRA XML export file, yielding one normalized
    ticket dict per <item> element.

    Memory management:
        - lxml iterparse processes one element at a time.
        - After yielding, element.clear() frees element content.
        - Sibling deletion loop frees the lxml tree structure itself.
          Without this, memory balloons even after element.clear().

    Args:
        xml_path: Absolute path to the JIRA XML export file.
        do_clean_html: Whether to clean HTML from text fields (default True).

    Yields:
        Normalized ticket dicts matching the JiraTicket schema.
    """
    from lxml import etree
    from services.jira.html_cleaner import clean_html

    logger.info(f"Starting streaming parse of: {xml_path}")
    ticket_count = 0
    error_count = 0

    context = etree.iterparse(xml_path, events=("end",), tag="item", recover=True)

    def _process_text(text: str) -> str:
        return clean_html(text) if do_clean_html else text

    for event, element in context:
        ticket_key = _safe_text(element.find("key"), default="UNKNOWN")

        try:
            custom = _extract_custom_fields(element)
            comments = _extract_comments(element, do_clean_html=do_clean_html)

            ticket: Dict[str, Any] = {
                "ticket_id":           ticket_key,
                "summary":             _process_text(_safe_text(element.find("summary"))),
                "description":         _process_text(_safe_text(element.find("description"))),
                "resolution":          _process_text(_safe_text(element.find("resolution"))),
                "resolution_details":  _process_text(custom.get("resolution_details", "")),
                "comments":            comments,
                "priority":            _normalize_metadata(_safe_text(element.find("priority"))),
                "status":              _normalize_metadata(_safe_text(element.find("status"))),
                "type":                _safe_text(element.find("type")),
                "assignee":            _safe_text(element.find("assignee")),
                "reporter":            _safe_text(element.find("reporter")),
                "created":             _safe_text(element.find("created")),
                "updated":             _safe_text(element.find("updated")),
                "resolved":            _safe_text(element.find("resolved")),
                # Custom fields — normalized for consistent filtering
                "city":                _normalize_metadata(custom.get("city", "")),
                "country":             "",   # Not in JIRA export schema; left empty
                "hcl_team":            _normalize_metadata(custom.get("hcl_team", "")),
                "impact":              _normalize_metadata(custom.get("impact", "")),
                "users_affected":      custom.get("users_affected", ""),
                "reported_source":     custom.get("reported_source", ""),
                "incident_noticed_at": custom.get("incident_noticed_at", ""),
                "ticket_transferred":  _normalize_metadata(custom.get("ticket_transferred", "")),
                "cat_pays":            custom.get("cat_pays", ""),
            }

            ticket_count += 1
            yield ticket

        except Exception as e:
            error_count += 1
            logger.error(
                "Failed to parse ticket",
                extra={"ticket_key": ticket_key, "error": str(e)}
            )

        finally:
            # CRITICAL: Clear element content AND remove previous siblings
            # element.clear() alone is not sufficient — the lxml tree
            # structure accumulates in memory without sibling deletion.
            element.clear()
            while element.getprevious() is not None:
                del element.getparent()[0]

    logger.info(
        "Streaming parse complete",
        extra={"total_parsed": ticket_count, "total_errors": error_count}
    )

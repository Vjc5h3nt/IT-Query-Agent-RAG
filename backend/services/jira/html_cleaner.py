"""
HTML cleaning utilities for JIRA XML ingestion.
Strips all HTML artifacts, email noise, and normalizes whitespace.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Compiled patterns for performance
_EMAIL_SIGNATURE_PATTERNS = [
    re.compile(r"(?im)^[\-]{2,}\s*$"),                      # -- separator
    re.compile(r"(?im)^(best\s+regards?|kind\s+regards?|thanks?(?:\s+and\s+regards?)?|sincerely|cheers|regards?)[,.]?\s*$"),
    re.compile(r"(?im)^\+?\d[\d\s\-().]{6,20}$"),           # phone numbers
    re.compile(r"(?im)^[A-Za-z ]+\s*\|\s*.+$"),             # "Name | Title | Company" lines
    re.compile(r"(?im)^from:\s+.+$"),                        # email forward headers
    re.compile(r"(?im)^(sent|date|subject|cc|bcc):\s+.+$"), # email header lines
    re.compile(r"(?im)^on .+ wrote:$"),                      # "On Mon, X wrote:" trigger
]

_ATTACHMENT_PATTERN = re.compile(
    r"\[.*?attached.*?\]|https?://\S+|!.*?!\s*$",
    re.IGNORECASE
)

_MULTI_WHITESPACE = re.compile(r"\s{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def clean_html(text: str) -> str:
    """
    Strip HTML tags and all common noise from JIRA text fields.

    Args:
        text: Raw HTML or plain text from JIRA XML.

    Returns:
        Clean, normalized plain text string. Empty string if input is
        None, blank, or produces no meaningful content.
    """
    if not text or not text.strip():
        return ""

    try:
        from bs4 import BeautifulSoup
        # Use lxml-xml parser for speed; fall back to html.parser
        try:
            soup = BeautifulSoup(text, "lxml")
        except Exception:
            soup = BeautifulSoup(text, "html.parser")

        # Remove embedded object / attachment error blocks
        for tag in soup.find_all(["object", "embed", "applet", "script", "style"]):
            tag.decompose()

        cleaned = soup.get_text(separator="\n")

    except Exception as e:
        # Fallback: strip tags with regex if BS4 fails unexpectedly
        logger.warning(f"BeautifulSoup failed, falling back to regex strip: {e}")
        cleaned = re.sub(r"<[^>]+>", " ", text)

    # Strip attachment links
    cleaned = _ATTACHMENT_PATTERN.sub("", cleaned)

    # Strip email signatures line by line
    lines = cleaned.splitlines()
    clean_lines = []
    skip_rest = False
    for line in lines:
        if skip_rest:
            break
        stripped = line.strip()
        if any(pat.match(stripped) for pat in _EMAIL_SIGNATURE_PATTERNS):
            # Signature detected — drop this line and everything after
            skip_rest = True
            continue
        clean_lines.append(line)

    cleaned = "\n".join(clean_lines)

    # Normalize whitespace
    cleaned = _MULTI_NEWLINE.sub("\n\n", cleaned)
    cleaned = _MULTI_WHITESPACE.sub(" ", cleaned)
    cleaned = cleaned.strip()

    return cleaned

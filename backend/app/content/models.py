"""
The stored shape of a processed content document.

Internal shape, as with users/models.py. Field names the implementation already
uses are kept (`uid`, `type`), and conversion to the shared contract happens in
contracts.py at the module boundary.
"""

import hashlib
from datetime import datetime, timezone

# Internal type names, and how they map to the shared contract's content_type
# enum. Two differ; the rest already match. The rename happens at the boundary,
# not in the database.
CONTENT_TYPES = {
    "pdf": "pdf",
    "research_paper": "research_paper",
    "text": "plain_text",          # renamed at the boundary
    "website": "website",
    "youtube": "youtube",
    "video": "uploaded_video",     # renamed at the boundary
}

STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


def content_fingerprint(text: str) -> str:
    """
    A stable hash of the extracted text, for duplicate detection.

    Foundation only, as the issue asks. Whitespace is normalised and case
    folded first, so the same document uploaded twice matches even if the
    extraction differs trivially between runs.

    Storing a hash rather than comparing full text means a duplicate check is a
    single indexed lookup instead of scanning every document the user owns.
    """
    normalised = " ".join((text or "").lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def build_content_doc(
    uid: str,
    content_type: str,
    title: str,
    chunks: list,
    *,
    source: str = None,
    language: str = "unknown",
    warnings: list = None,
    technical_terms: list = None,
    glossary: list = None,
    extra: dict = None,
) -> dict:
    """
    `extra` carries processor-specific metadata such as abstract_detected.
    It is stored but deliberately NOT sent in the shared contract, which sets
    additionalProperties: false — agreed during the contract review that the
    contract is an exchange format, not a dump of internal variables.
    """
    now = datetime.now(timezone.utc)
    return {
        "schema_version": "1.0",
        "uid": uid,
        "type": content_type,
        "title": (title or "Untitled")[:300],
        "source": source,
        "status": STATUS_READY,
        "language": language,
        "warnings": warnings or [],
        "technical_terms": technical_terms or [],
        "glossary": glossary or [],
        "chunks": chunks,
        "fingerprint": content_fingerprint(" ".join(c["text"] for c in chunks)),
        "extra": extra or {},
        "created_at": now,
        "updated_at": now,
    }

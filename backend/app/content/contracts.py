"""
Boundary conversion between the stored content document and the shared contract.

Same arrangement as users/contracts.py: the shared contracts define what modules
send each other, not how this module stores data. So `uid` and `type` stay as
they are in MongoDB, and the renaming happens here, once.

If you add a field: change models.py, then map it here.
"""

from datetime import datetime, timezone

from app.content.models import CONTENT_TYPES

SCHEMA_VERSION = "1.0"

# Only these keys are allowed on a chunk. The contract sets
# additionalProperties: false, so anything else would cause the whole document
# to be rejected.
CHUNK_FIELDS = (
    "chunk_id",
    "order",
    "section_title",
    "text",
    "page_number",
    "start_time_seconds",
    "end_time_seconds",
    "is_critical",
)


def _iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value) if value is not None else datetime.now(timezone.utc).isoformat()


def _chunk_to_contract(chunk: dict) -> dict:
    out = {k: chunk[k] for k in CHUNK_FIELDS if k in chunk}
    # chunk_id must be a string; order must be present. Both were agreed in the
    # contract review and are produced by chunking.py, but a document written
    # before that change could still be missing them.
    out["chunk_id"] = str(out.get("chunk_id", ""))
    if "order" not in out:
        out["order"] = 0
    return out


def to_contract(doc: dict, *, include_chunks: bool = True) -> dict:
    """
    Convert a stored content document into content.schema.json shape.

    Renames applied here (internal -> contract):
        uid  -> user_id
        type -> content_type  ("text" -> "plain_text", "video" -> "uploaded_video")
        _id  -> content_id

    `extra` (e.g. abstract_detected) is deliberately not included: the contract
    forbids extra fields, and it was agreed during review that processor
    metadata stays internal to this module.
    """
    chunks = doc.get("chunks") or []

    contract = {
        "schema_version": SCHEMA_VERSION,
        "content_id": str(doc.get("content_id") or doc.get("_id") or ""),
        "user_id": doc.get("uid"),
        "content_type": CONTENT_TYPES.get(doc.get("type"), doc.get("type")),
        "title": doc.get("title"),
        "source": doc.get("source"),
        "status": doc.get("status", "ready"),
        # language and warnings are REQUIRED by the contract. The agreed
        # placeholders are "unknown" and [], so a consumer always finds the
        # field present rather than having to handle it being absent.
        "language": doc.get("language") or "unknown",
        "warnings": doc.get("warnings") or [],
        "created_at": _iso(doc.get("created_at")),
    }

    if doc.get("technical_terms"):
        contract["technical_terms"] = doc["technical_terms"]
    if doc.get("glossary"):
        contract["glossary"] = doc["glossary"]

    if include_chunks:
        contract["chunks"] = [_chunk_to_contract(c) for c in chunks]

    return contract


def to_summary(doc: dict) -> dict:
    """
    Listing entry — metadata only, no chunk text.

    A learner with fifty uploads should not pull every word of every document
    just to render a list.
    """
    return {
        "content_id": str(doc.get("content_id") or doc.get("_id") or ""),
        "title": doc.get("title"),
        "content_type": CONTENT_TYPES.get(doc.get("type"), doc.get("type")),
        "status": doc.get("status", "ready"),
        "language": doc.get("language") or "unknown",
        "warnings": doc.get("warnings") or [],
        "chunk_count": len(doc.get("chunks") or []),
        "created_at": _iso(doc.get("created_at")),
    }

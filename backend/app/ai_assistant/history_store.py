"""
Fail-silent store for the learner's persistent assistant conversation.

Same contract as app/intervention/store.py: a database problem must never
turn a successful assistant answer, or a successful content generation,
into an error response - every function here returns rather than raises.

uid-keyed, not session_id-keyed: the design is one continuous conversation
per learner (confirmed 2026-09-30), not one per study session. session_id/
content_id/chunk_id are recorded on each turn for context, not as the
partition key.
"""

import logging
import time
import uuid

from app.core.db import db

log = logging.getLogger(__name__)


def insert_message(
    *,
    uid: str,
    role: str,
    content: str,
    source: str,
    trigger: str | None = None,
    content_id: str | None = None,
    chunk_id: str | None = None,
    session_id: str | None = None,
) -> bool:
    """Append one turn. Returns whether it was stored."""
    document = {
        "_id": str(uuid.uuid4()),
        "uid": uid,
        "timestamp": time.time(),
        "role": role,
        "content": content,
        "source": source,
        "trigger": trigger,
        "content_id": content_id,
        "chunk_id": chunk_id,
        "session_id": session_id,
    }
    try:
        db.assistant_messages.insert_one(document)
        return True
    except Exception:
        log.warning("assistant message for %s could not be stored", uid, exc_info=True)
        return False


def list_messages(uid: str, limit: int = 50, before: float | None = None) -> list[dict]:
    """This learner's own history, newest first. before is an exclusive
    upper bound on timestamp, for paging further back."""
    query: dict = {"uid": uid}
    if before is not None:
        query["timestamp"] = {"$lt": before}
    try:
        cursor = db.assistant_messages.find(query).sort("timestamp", -1).limit(limit)
        return list(cursor)
    except Exception:
        log.warning("assistant history for %s could not be read", uid, exc_info=True)
        return []

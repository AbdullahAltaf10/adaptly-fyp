"""Repositories for session records and per-chunk progress.

Sessions are mutable while a study session is active (status, current chunk,
counters), so writes go through an upsert that preserves ``created_at`` and
refreshes ``updated_at`` on every call rather than replacing the whole
document.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import collections
from .base import format_timestamp, strip_storage_id, utc_now
from .field_allowlists import CHUNK_PROGRESS_FIELDS, SESSION_FIELDS, filtered


class SessionRepository:
    def __init__(self, database: Any) -> None:
        self._collection = database[collections.SESSIONS]

    def upsert_session(
        self, session: Mapping[str, Any], *, now: Any = None
    ) -> None:
        session_id = session["session_id"]
        now_str = format_timestamp(now or utc_now())
        document = filtered(dict(session), SESSION_FIELDS)
        document.pop("created_at", None)
        document["updated_at"] = now_str
        self._collection.update_one(
            {"_id": session_id},
            {
                "$set": document,
                "$setOnInsert": {"created_at": now_str},
            },
            upsert=True,
        )

    def get(self, session_id: str) -> dict[str, Any] | None:
        return strip_storage_id(self._collection.find_one({"_id": session_id}))

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        cursor = self._collection.find({"user_id": user_id}).sort("started_at", 1)
        return [strip_storage_id(document) for document in cursor]


class ChunkProgressRepository:
    """Per-(session, chunk) progress. No shared contract yet (Issue #27 only
    asks for persistence support, not a new schema file), so the stored shape
    is intentionally minimal and matches the issue's field list exactly.
    """

    def __init__(self, database: Any) -> None:
        self._collection = database[collections.CHUNK_PROGRESS]

    @staticmethod
    def _document_id(session_id: str, chunk_id: str) -> str:
        return f"{session_id}::{chunk_id}"

    def upsert_progress(self, progress: Mapping[str, Any]) -> None:
        """Merge in whichever fields are provided (entered vs. completed)."""

        session_id = progress["session_id"]
        chunk_id = progress["chunk_id"]
        document = filtered(dict(progress), CHUNK_PROGRESS_FIELDS)
        set_fields = {key: value for key, value in document.items() if value is not None}
        self._collection.update_one(
            {"_id": self._document_id(session_id, chunk_id)},
            {"$set": set_fields},
            upsert=True,
        )

    def get(self, session_id: str, chunk_id: str) -> dict[str, Any] | None:
        return strip_storage_id(
            self._collection.find_one(
                {"_id": self._document_id(session_id, chunk_id)}
            )
        )

    def list_by_session(self, session_id: str) -> list[dict[str, Any]]:
        cursor = self._collection.find({"session_id": session_id})
        return [strip_storage_id(document) for document in cursor]

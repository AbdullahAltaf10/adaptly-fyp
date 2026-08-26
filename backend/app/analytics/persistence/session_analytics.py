"""Repository for computed Module 8 session summaries.

Stores the deterministic output of ``domain.metrics.build_session_summary``
(Issue #26). The contract-shaped summary is kept verbatim under the
``summary`` key; a thin envelope around it (``insight_report_status``,
``created_at``/``updated_at``) carries persistence-only bookkeeping that
``session-summary.schema.json`` intentionally does not define, since that
schema is the wire/API contract for the summary itself, not this storage
row. ``insight_report_status`` mirrors the status enum from
``analytics-report.schema.json`` and starts at ``"pending"`` until Issue #32
(Gemini insight report) fills it in.

Idempotency: keyed by ``(session_id, metric_version)``. Re-running summary
generation for a session that already has a summary at that metric version
overwrites the same document instead of creating a duplicate.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import collections
from .base import format_timestamp, strip_storage_id, utc_now
from .field_allowlists import SESSION_SUMMARY_FIELDS, filtered


class SessionAnalyticsRepository:
    def __init__(self, database: Any) -> None:
        self._collection = database[collections.SESSION_ANALYTICS]

    @staticmethod
    def _document_id(session_id: str, metric_version: str) -> str:
        return f"{session_id}::{metric_version}"

    def save(
        self,
        summary: Mapping[str, Any],
        *,
        insight_report_status: str = "pending",
        now: Any = None,
    ) -> str:
        session_id = summary["session_id"]
        metric_version = summary["metric_version"]
        now_str = format_timestamp(now or utc_now())
        document = {
            "session_id": session_id,
            "user_id": summary["user_id"],
            "content_id": summary["content_id"],
            "metric_version": metric_version,
            "completed_at": summary["completed_at"],
            "summary": filtered(dict(summary), SESSION_SUMMARY_FIELDS),
            "insight_report_status": insight_report_status,
            "updated_at": now_str,
        }
        doc_id = self._document_id(session_id, metric_version)
        self._collection.update_one(
            {"_id": doc_id},
            {"$set": document, "$setOnInsert": {"created_at": now_str}},
            upsert=True,
        )
        return doc_id

    def get(self, session_id: str, metric_version: str) -> dict[str, Any] | None:
        return strip_storage_id(
            self._collection.find_one(
                {"_id": self._document_id(session_id, metric_version)}
            )
        )

    def list_by_session(self, session_id: str) -> list[dict[str, Any]]:
        cursor = self._collection.find({"session_id": session_id}).sort(
            "metric_version", 1
        )
        return [strip_storage_id(document) for document in cursor]

    def list_by_user(
        self, user_id: str, *, since: str | None = None, before: str | None = None
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"user_id": user_id}
        if since is not None or before is not None:
            completed_at_range: dict[str, Any] = {}
            if since is not None:
                completed_at_range["$gte"] = since
            if before is not None:
                completed_at_range["$lte"] = before
            query["completed_at"] = completed_at_range
        cursor = self._collection.find(query).sort("completed_at", 1)
        return [strip_storage_id(document) for document in cursor]

    def set_insight_report_status(
        self, session_id: str, metric_version: str, status: str, *, now: Any = None
    ) -> None:
        now_str = format_timestamp(now or utc_now())
        self._collection.update_one(
            {"_id": self._document_id(session_id, metric_version)},
            {"$set": {"insight_report_status": status, "updated_at": now_str}},
        )

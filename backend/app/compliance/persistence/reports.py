"""Repository for Module 10 compliance reports (Issue #74).

One report per session: keyed by ``session_id`` directly (unlike Module 8's
session-analytics documents, which key on ``(session_id, metric_version)``
because a session can be re-summarized under a new metric version -- a
compliance report intentionally has no equivalent "recompute under a new
version" path yet, so one report per session is the whole contract for now).

The contract-shaped report is kept verbatim under a ``report`` key, exactly
the way Module 8's ``SessionAnalyticsRepository`` keeps its contract-shaped
summary under a ``summary`` key: ``compliance-report.schema.json`` sets
``additionalProperties: false``, so persistence-only bookkeeping
(``created_at``/``updated_at``) must live outside the contract-shaped
payload, never mixed into it -- otherwise returning the stored document
verbatim from an API endpoint would fail its own contract.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import collections
from .base import format_timestamp, strip_storage_id, utc_now
from .field_allowlists import COMPLIANCE_REPORT_FIELDS, filtered


class ComplianceReportRepository:
    def __init__(self, database: Any) -> None:
        self._collection = database[collections.COMPLIANCE_REPORTS]

    def save(self, report: Mapping[str, Any], *, now: Any = None) -> str:
        session_id = report["session_id"]
        now_str = format_timestamp(now or utc_now())
        document = {
            "session_id": session_id,
            "user_id": report["user_id"],
            "content_id": report["content_id"],
            "report": filtered(dict(report), COMPLIANCE_REPORT_FIELDS),
            "updated_at": now_str,
        }
        self._collection.update_one(
            {"_id": session_id},
            {"$set": document, "$setOnInsert": {"created_at": now_str}},
            upsert=True,
        )
        return session_id

    def get(self, session_id: str) -> dict[str, Any] | None:
        return strip_storage_id(self._collection.find_one({"_id": session_id}))

    def list(
        self,
        *,
        user_id: str | None = None,
        content_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if user_id is not None:
            query["user_id"] = user_id
        if content_id is not None:
            query["content_id"] = content_id
        cursor = self._collection.find(query).sort(
            [("report.generated_at", -1), ("session_id", -1)]
        )
        return [strip_storage_id(document) for document in cursor]

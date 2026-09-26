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
(``created_at``) must live outside the contract-shaped payload, never mixed
into it -- otherwise returning the stored document verbatim from an API
endpoint would fail its own contract.

``save`` is insert-only (Issue #74 review finding): the first call for a
``session_id`` wins and every later call is a no-op against the stored
document, using ``$setOnInsert`` rather than ``$set``. A ``$set``-based
upsert let two concurrent ``generate_report`` calls for the same session
race -- the second write would silently overwrite the first report with a
different one, even though ``generate_report`` itself intends generation to
be idempotent. ``$setOnInsert`` closes that race at the database level:
whichever write reaches MongoDB first is the one that sticks, and the
caller who "lost" the race gets that same stored document back (see
``service/generation.py``, which now reads the report back after saving
rather than trusting its own locally-built one).
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
        """Insert-only: the first report saved for a session_id is the one
        that sticks. A later call is a no-op against whatever is already
        stored -- see the module docstring for why this must never be a
        ``$set`` upsert.
        """

        session_id = report["session_id"]
        now_str = format_timestamp(now or utc_now())
        document = {
            "session_id": session_id,
            "user_id": report["user_id"],
            "content_id": report["content_id"],
            "report": filtered(dict(report), COMPLIANCE_REPORT_FIELDS),
            "created_at": now_str,
        }
        self._collection.update_one(
            {"_id": session_id},
            {"$setOnInsert": document},
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

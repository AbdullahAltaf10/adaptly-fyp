"""Repository for Module 8's per-session insight report (Issue #32).

One report per session: regenerating it (a retry, or the first-ever attempt)
replaces the same document instead of creating a new one, the same pattern
already used for session summaries (``session_analytics.py``, keyed by
session_id + metric_version) and learning profiles (``learning_profiles.py``,
keyed by user_id). Keyed here by ``session_id`` alone, since a session has
exactly one insight report regardless of how many times generation is
retried — ``retry_count``/``last_attempted_at`` on the stored document track
the retry history instead of keeping old rows around.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import collections
from .base import strip_storage_id
from .field_allowlists import ANALYTICS_REPORT_FIELDS, filtered


class InsightReportRepository:
    def __init__(self, database: Any) -> None:
        self._collection = database[collections.INSIGHT_REPORTS]

    def save(self, report: Mapping[str, Any]) -> None:
        session_id = report["session_id"]
        document = filtered(dict(report), ANALYTICS_REPORT_FIELDS)
        self._collection.update_one(
            {"_id": session_id}, {"$set": document}, upsert=True
        )

    def get(self, session_id: str) -> dict[str, Any] | None:
        return strip_storage_id(self._collection.find_one({"_id": session_id}))

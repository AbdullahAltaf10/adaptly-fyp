"""Repository for multi-session learning profiles.

One profile per learner. Recomputing a profile (Issue #33 will do the actual
aggregation) simply replaces the existing document for that ``user_id`` —
profiles are derived/recomputable by design, never accumulated.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import collections
from .base import format_timestamp, strip_storage_id, utc_now
from .field_allowlists import LEARNING_PROFILE_FIELDS, filtered


class LearningProfileRepository:
    def __init__(self, database: Any) -> None:
        self._collection = database[collections.LEARNING_PROFILES]

    def save(self, profile: Mapping[str, Any], *, now: Any = None) -> None:
        user_id = profile["user_id"]
        now_str = format_timestamp(now or utc_now())
        document = filtered(dict(profile), LEARNING_PROFILE_FIELDS)
        document["updated_at"] = now_str
        self._collection.update_one(
            {"_id": user_id},
            {"$set": document, "$setOnInsert": {"created_at": now_str}},
            upsert=True,
        )

    def get(self, user_id: str) -> dict[str, Any] | None:
        return strip_storage_id(self._collection.find_one({"_id": user_id}))

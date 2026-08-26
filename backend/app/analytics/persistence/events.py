"""Repositories for the three Module 8 raw event streams.

Engagement, intervention, and assistant events share one storage shape:
each has a natural unique id, belongs to exactly one session, and is queried
back in session order. ``EventRepository`` implements that shared behavior
once; the three public repositories just bind it to a collection, id field,
and the contract's allow-listed fields.

Idempotency: each event's natural id (``event_id`` / ``intervention_id``) is
used as the MongoDB ``_id``. Re-submitting the same event replaces the same
document instead of creating a second one, so duplicate submissions can never
double-count in later metric calculations.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import collections
from .base import strip_storage_id
from .field_allowlists import (
    ASSISTANT_EVENT_FIELDS,
    ENGAGEMENT_EVENT_FIELDS,
    INTERVENTION_EVENT_FIELDS,
    filtered,
)


class EventRepository:
    def __init__(
        self,
        database: Any,
        *,
        collection_name: str,
        id_field: str,
        allowed_fields: set[str],
    ) -> None:
        self._collection = database[collection_name]
        self._id_field = id_field
        self._allowed_fields = allowed_fields

    def insert_events(
        self, events: Sequence[Mapping[str, Any]]
    ) -> dict[str, int]:
        """Idempotently store events, keyed by their contract id field."""

        inserted = 0
        updated = 0
        for event in events:
            event_id = event[self._id_field]
            document = filtered(dict(event), self._allowed_fields)
            document["_id"] = event_id
            result = self._collection.replace_one(
                {"_id": event_id}, document, upsert=True
            )
            if result.upserted_id is not None:
                inserted += 1
            else:
                updated += 1
        return {"inserted": inserted, "updated": updated}

    def get(self, event_id: str) -> dict[str, Any] | None:
        return strip_storage_id(self._collection.find_one({"_id": event_id}))

    def list_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return a session's events in chronological order.

        Contract timestamps are fixed-format ISO 8601 UTC (``...Z``), so a
        plain string sort already yields chronological order.
        """

        cursor = self._collection.find({"session_id": session_id}).sort(
            "timestamp", 1
        )
        return [strip_storage_id(document) for document in cursor]

    def count_for_session(self, session_id: str) -> int:
        return self._collection.count_documents({"session_id": session_id})


class EngagementEventRepository(EventRepository):
    def __init__(self, database: Any) -> None:
        super().__init__(
            database,
            collection_name=collections.ENGAGEMENT_EVENTS,
            id_field="event_id",
            allowed_fields=ENGAGEMENT_EVENT_FIELDS,
        )


class InterventionEventRepository(EventRepository):
    def __init__(self, database: Any) -> None:
        super().__init__(
            database,
            collection_name=collections.INTERVENTION_EVENTS,
            id_field="intervention_id",
            allowed_fields=INTERVENTION_EVENT_FIELDS,
        )


class AssistantEventRepository(EventRepository):
    def __init__(self, database: Any) -> None:
        super().__init__(
            database,
            collection_name=collections.ASSISTANT_EVENTS,
            id_field="event_id",
            allowed_fields=ASSISTANT_EVENT_FIELDS,
        )

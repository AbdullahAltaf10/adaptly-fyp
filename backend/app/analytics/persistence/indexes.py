"""Index setup for the Module 8 analytics collections (Issue #27).

``create_index`` is itself idempotent (an existing index with the same spec
is a no-op), so calling ``ensure_indexes`` on every app startup is safe. Most
collections also key their documents' ``_id`` by the natural id
(``session_id``, ``event_id``, ...), which already guarantees uniqueness;
the matching field-level unique indexes below are created anyway so the
indexes requested by the issue are queryable/verifiable by field name, not
only via ``_id``.
"""

from __future__ import annotations

from typing import Any

from . import collections


def ensure_indexes(database: Any) -> None:
    sessions = database[collections.SESSIONS]
    sessions.create_index("session_id", unique=True, name="uniq_session_id")
    sessions.create_index(
        [("user_id", 1), ("started_at", 1)], name="user_id_started_at"
    )
    sessions.create_index("status", name="status")

    engagement_events = database[collections.ENGAGEMENT_EVENTS]
    engagement_events.create_index("event_id", unique=True, name="uniq_event_id")
    engagement_events.create_index(
        [("session_id", 1), ("timestamp", 1)], name="session_id_timestamp"
    )
    engagement_events.create_index(
        [("content_id", 1), ("chunk_id", 1)], name="content_id_chunk_id"
    )

    intervention_events = database[collections.INTERVENTION_EVENTS]
    intervention_events.create_index(
        "intervention_id", unique=True, name="uniq_intervention_id"
    )
    intervention_events.create_index(
        [("session_id", 1), ("timestamp", 1)], name="session_id_timestamp"
    )
    intervention_events.create_index(
        [("intervention_type", 1), ("outcome", 1)], name="intervention_type_outcome"
    )

    assistant_events = database[collections.ASSISTANT_EVENTS]
    assistant_events.create_index("event_id", unique=True, name="uniq_event_id")
    assistant_events.create_index(
        [("session_id", 1), ("timestamp", 1)], name="session_id_timestamp"
    )

    chunk_progress = database[collections.CHUNK_PROGRESS]
    chunk_progress.create_index(
        [("session_id", 1), ("chunk_id", 1)], unique=True, name="uniq_session_chunk"
    )
    chunk_progress.create_index(
        [("content_id", 1), ("chunk_id", 1)], name="content_id_chunk_id"
    )

    session_analytics = database[collections.SESSION_ANALYTICS]
    session_analytics.create_index(
        [("session_id", 1), ("metric_version", 1)],
        unique=True,
        name="uniq_session_metric_version",
    )
    session_analytics.create_index(
        [("user_id", 1), ("completed_at", 1)], name="user_id_completed_at"
    )

    learning_profiles = database[collections.LEARNING_PROFILES]
    learning_profiles.create_index("user_id", unique=True, name="uniq_user_id")

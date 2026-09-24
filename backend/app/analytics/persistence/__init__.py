"""Module 8 analytics persistence layer (Issue #27).

Repository/service boundary around MongoDB, kept entirely separate from
``backend/app/analytics/domain`` (Issue #26's pure metric engine, which must
never import MongoDB). Callers pass a ``pymongo.database.Database`` (from
``client.get_database``) in production, or a ``mongomock`` database in tests.
"""

from __future__ import annotations

from . import collections
from .client import get_database
from .events import (
    AssistantEventRepository,
    EngagementEventRepository,
    EventRepository,
    InterventionEventRepository,
)
from .indexes import ensure_indexes
from .learning_profiles import LearningProfileRepository
from .session_analytics import SessionAnalyticsRepository
from .sessions import ChunkProgressRepository, SessionRepository

__all__ = [
    "collections",
    "get_database",
    "ensure_indexes",
    "EventRepository",
    "EngagementEventRepository",
    "InterventionEventRepository",
    "AssistantEventRepository",
    "SessionRepository",
    "ChunkProgressRepository",
    "SessionAnalyticsRepository",
    "LearningProfileRepository",
]

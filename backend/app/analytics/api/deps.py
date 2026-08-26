"""FastAPI dependency for obtaining Module 8's repository bundle.

Kept separate from the endpoint functions so tests can override it
(``app.dependency_overrides[get_repositories] = ...``) with a mongomock-backed
instance instead of a real MongoDB connection — the same pattern used for
``get_current_user_id`` in ``backend/app/api/deps.py``.
"""

from __future__ import annotations

from backend.app.analytics.persistence.client import get_database
from backend.app.analytics.service.finalization import AnalyticsRepositories


def get_repositories() -> AnalyticsRepositories:
    return AnalyticsRepositories.from_database(get_database())

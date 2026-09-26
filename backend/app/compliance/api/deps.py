"""FastAPI dependency for obtaining Module 10's repository bundle.

Kept separate from endpoint functions so tests can override it
(``app.dependency_overrides[get_repositories] = ...``) with a mongomock-backed
instance, the same pattern Module 8's own ``analytics/api/deps.py`` uses.
"""

from __future__ import annotations

from backend.app.compliance.persistence.client import get_database
from backend.app.compliance.service.generation import ComplianceRepositories


def get_repositories() -> ComplianceRepositories:
    database = get_database()
    return ComplianceRepositories.from_database(database, database)

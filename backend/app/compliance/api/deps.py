"""FastAPI dependency for obtaining Module 10's repository bundle.

Kept separate from endpoint functions so tests can override it
(``app.dependency_overrides[get_repositories] = ...``) with a mongomock-backed
instance, the same pattern Module 8's own ``analytics/api/deps.py`` uses.
"""

from __future__ import annotations

from app.analytics.persistence.client import get_database
from app.compliance.service.generation import ComplianceRepositories


def get_repositories() -> ComplianceRepositories:
    # Module 8's cached client (#66): one pooled MongoClient per process,
    # shared with every other module, instead of a new client per request.
    database = get_database()
    return ComplianceRepositories.from_database(database, database)

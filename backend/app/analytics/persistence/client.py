"""Real MongoDB connection factory for Module 8 analytics.

Only imported when the app actually connects to Atlas; tests never import
this module — they construct repositories directly against a mongomock (or
other in-memory) database instead. Kept separate so the test suite has zero
dependency on real network/TLS setup.
"""

from __future__ import annotations

import os

import certifi
import pymongo
from pymongo.database import Database


def get_database(mongo_uri: str | None = None, db_name: str | None = None) -> Database:
    """Connect using ``MONGO_URI``/``DB_NAME`` (see ``backend/.env.example``).

    ``certifi``'s CA bundle is required for Atlas TLS on Windows — without it,
    writes fail silently instead of raising (see ``backend/README.md``).
    """

    uri = mongo_uri or os.environ["MONGO_URI"]
    name = db_name or os.environ["DB_NAME"]
    client = pymongo.MongoClient(uri, tlsCAFile=certifi.where())
    return client[name]

"""Real MongoDB connection factory for Module 10 compliance storage.

Deliberately duplicates Module 8's own ``analytics/persistence/client.py``
rather than importing it: Module 10 does not take a hard dependency on
Module 8's persistence package just to open a database handle, the same way
Module 8's persistence package takes no such dependency on any other
module. Both connect to the same ``MONGO_URI``/``DB_NAME`` -- one MongoDB
database, many collections, exactly as CLAUDE.md's (renamed to
PROJECT_CONTEXT.md by PR #64) architecture section describes.

Only imported when the app actually connects to Atlas; tests never import
this module -- they construct repositories directly against a mongomock (or
other in-memory) database instead.
"""

from __future__ import annotations

import os

import certifi
import pymongo
from pymongo.database import Database


def get_database(mongo_uri: str | None = None, db_name: str | None = None) -> Database:
    uri = mongo_uri or os.environ["MONGO_URI"]
    name = db_name or os.environ["DB_NAME"]
    client = pymongo.MongoClient(uri, tlsCAFile=certifi.where())
    return client[name]

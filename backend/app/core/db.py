"""
MongoDB connection.

Two deliberate behaviours here, both fixing problems carried over from the
prototype:

1. **Lazy connection.** The prototype connected at import time, so simply
   importing the application required configured credentials. That made the
   test suite and any tooling depend on a live database. The connection is now
   made on first actual use.

2. **A clear error instead of a confusing one.** With DB_NAME unset, the
   prototype failed with `TypeError: name must be an instance of str, not
   <class 'NoneType'>` raised from deep inside pymongo, which says nothing
   about the real problem. Missing configuration now reports exactly what is
   missing and where to set it.
"""

import os

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

# backend/.env  (this file is app/core/db.py, so go up three levels)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(dotenv_path=_ENV_PATH)

_client = None
_database = None


def _connect():
    global _client, _database
    if _database is not None:
        return _database

    uri = os.getenv("MONGO_URI")
    name = os.getenv("DB_NAME")

    missing = [n for n, v in (("MONGO_URI", uri), ("DB_NAME", name)) if not v]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy backend/.env.example to backend/.env and fill them in."
        )

    # certifi is REQUIRED for MongoDB Atlas on Windows. Without tlsCAFile the
    # connection appears to succeed and writes silently never arrive.
    _client = MongoClient(uri, tlsCAFile=certifi.where())
    _database = _client[name]
    return _database


class _LazyDatabase:
    """
    Stands in for the database object so `db.users.find_one(...)` still reads
    naturally, while the actual connection is deferred until first use.
    """

    def __getattr__(self, name):
        return getattr(_connect(), name)

    def __getitem__(self, name):
        return _connect()[name]


db = _LazyDatabase()

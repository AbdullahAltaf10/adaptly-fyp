"""Real MongoDB connection factory for Module 8 analytics.

Only imported when the app actually connects to Atlas; tests never import
this module — they construct repositories directly against a mongomock (or
other in-memory) database instead. Kept separate so the test suite has zero
dependency on real network/TLS setup.

``get_database`` is called from a *per-request* FastAPI dependency
(``analytics/api/deps.py``), so it must not build a new client each time.
Every ``MongoClient`` opens its own connection pool (100 sockets by default)
and its own monitor threads, and nothing closes them once the request ends —
on Atlas's 500-connection free tier that exhausts the cluster, and the
symptom lands on whichever module happens to connect next rather than here.
The client is therefore built once per distinct target and reused. See
Issue #59.

Deliberately not delegating to ``app.core.db``: that module resolves exactly
one database from the environment, while this one has to keep accepting an
explicit ``mongo_uri``/``db_name`` so it stays usable against a throwaway
database without touching global state. Two pooled clients for the process
is bounded and fine; hundreds of unpooled ones is not.
"""

from __future__ import annotations

import os
import threading

import certifi
import pymongo
from pymongo.database import Database

# Keyed by (uri, db_name) so an explicit target gets its own client rather
# than silently reusing one pointed somewhere else.
_clients: dict[tuple[str, str], pymongo.MongoClient] = {}
_lock = threading.Lock()


def get_database(mongo_uri: str | None = None, db_name: str | None = None) -> Database:
    """Return the database, reusing one pooled client per ``(uri, db_name)``.

    ``certifi``'s CA bundle is required for Atlas TLS on Windows — without it,
    writes fail silently instead of raising (see ``backend/README.md``).
    """

    uri = mongo_uri or os.environ["MONGO_URI"]
    name = db_name or os.environ["DB_NAME"]
    key = (uri, name)

    client = _clients.get(key)
    if client is None:
        with _lock:
            # Re-check inside the lock: two requests can race here on startup,
            # and losing that race must not leak a second pool.
            client = _clients.get(key)
            if client is None:
                client = pymongo.MongoClient(uri, tlsCAFile=certifi.where())
                _clients[key] = client
    return client[name]

"""
Bridges Module 3's engagement events into Module 8's analytics.

Calls EngagementEventRepository directly (unlike intervention/store.py,
this isn't a stand-in — Module 8's real repository already exists and is
merged). Uses app.core.db.db, the same lazy-singleton connection Module 4
already reuses for this same purpose, rather than opening a second
connection path through analytics.persistence.client.

Failure behaviour matches intervention/store.py: this must never raise.
Module 3's /analyze endpoint is on the hot path for every 10-frame window;
an unreachable database must not take engagement detection down.
"""

import logging

from app.analytics.persistence.events import EngagementEventRepository
from app.core.db import db

log = logging.getLogger(__name__)


def record_engagement_event(event: dict) -> bool:
    """Write one engagement event. Returns whether it was stored."""
    try:
        EngagementEventRepository(db).insert_events([event])
        return True
    except Exception:
        log.warning("engagement event %s could not be stored", event.get("event_id"), exc_info=True)
        return False

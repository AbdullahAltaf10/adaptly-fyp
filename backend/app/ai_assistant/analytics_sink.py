"""
Bridges Module 5's assistant events into Module 8's analytics.

Calls AssistantEventRepository directly (unlike intervention/store.py,
this isn't a stand-in — Module 8's real repository already exists and is
merged). Uses app.core.db.db, the same lazy-singleton connection Module
3/4's sinks already reuse for this same purpose, rather than opening a
second connection path through analytics.persistence.client.

One call, both events: an exchange is always a (learner, assistant) pair
(see analytics_contracts.py) and they are written together in a single
insert_events call rather than two separate writes, so a caller never
observes one half of an exchange stored without the other.

Failure behaviour matches the other sinks: this must never raise.
Module 5's /assistant/messages is a learner-facing request/response
endpoint; an unreachable database must not turn a successful answer into
a failed request.
"""

import logging

from app.analytics.persistence.events import AssistantEventRepository
from app.core.db import db

log = logging.getLogger(__name__)


def record_assistant_exchange(learner_event: dict, assistant_event: dict) -> bool:
    """Write one exchange's pair of events. Returns whether it was stored."""
    try:
        AssistantEventRepository(db).insert_events([learner_event, assistant_event])
        return True
    except Exception:
        log.warning(
            "assistant exchange %s/%s could not be stored",
            learner_event.get("event_id"),
            assistant_event.get("event_id"),
            exc_info=True,
        )
        return False

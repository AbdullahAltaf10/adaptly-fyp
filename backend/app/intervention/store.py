"""
Thin, fail-silent wrapper around Module 8's real InterventionEventRepository.

History: this used to be a full stand-in that hand-rolled its own Mongo
writes and its own duplicated field allowlist, because Module 8's real
repository didn't exist yet on develop. It does now (merged via #63), so
this file no longer duplicates any storage logic - every function below
just delegates to InterventionEventRepository.

What THIS file still owns, and why it still exists rather than being
deleted: InterventionEventRepository has no fail-silent behavior of its
own - a Mongo error propagates as an exception. Module 4 hangs off Module
3's analyze endpoint, and an unreachable database must not take engagement
detection down - that is a working feature and intervention delivery is
not worth breaking it over. Every function here still returns rather than
raises, same contract as before, so service.py and routes.py need zero
changes.

KNOWN FOLLOW-UP (deliberately not done here - see PR for Issue #34):
the fully "correct" end state this file always pointed to is for
service.py and routes.py to call InterventionEventRepository directly and
for this file to be deleted entirely. That refactor touches 6 call sites
across the two files Module 4 owns (service.py, routes.py), requires
renaming list_for_session -> list_by_session and save(event) ->
insert_events([event]) at each site, and re-adding this file's try/except
resilience individually at all 6 sites, since the repository provides
none of its own. Left as a scoped, lower-risk follow-up rather than done
alongside Issue #34, to limit blast radius this close to the FYP defense.
"""

import logging

from app.analytics.persistence.events import InterventionEventRepository
from app.core.db import db

log = logging.getLogger(__name__)


def _repo() -> InterventionEventRepository:
    return InterventionEventRepository(db)


def save(event: dict) -> bool:
    """Write one event, replacing any previous version of it. Returns whether it was stored."""
    try:
        _repo().insert_events([event])
        return True
    except Exception:
        log.warning("intervention %s could not be stored", event.get("intervention_id"), exc_info=True)
        return False


def get(intervention_id: str) -> dict | None:
    try:
        return _repo().get(intervention_id)
    except Exception:
        log.warning("intervention %s could not be read", intervention_id, exc_info=True)
        return None


def list_for_session(session_id: str) -> list:
    """This session's interventions, oldest first."""
    try:
        return _repo().list_by_session(session_id)
    except Exception:
        log.warning("interventions for session %s could not be read", session_id, exc_info=True)
        return []

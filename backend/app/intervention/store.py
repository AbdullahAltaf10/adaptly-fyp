"""
Where intervention events are written.

This is a deliberate stand-in, not a design
-------------------------------------------
Module 8 already owns this storage. On `feature/29-module-8-apis` there is an
`InterventionEventRepository` that writes the same documents, to the same
collection, keyed the same way. The right long-term arrangement is for Module 4
to call that repository and for this file to disappear.

It cannot do that today: Module 8 is not merged into develop, and #39-#42 are
still open. Waiting would leave Module 4 unable to record anything, and an
intervention that is never written is invisible to every metric downstream.

So this file exists to be thrown away, and everything about it is chosen so
that throwing it away costs nothing:

  * the same collection name - analytics_intervention_events
  * the same `_id` - the intervention_id, so re-submitting one event replaces
    its document rather than adding a second
  * the same allowlist filtering before the write

Documents written here are therefore already exactly what Module 8's
repository would have written, and no migration is needed when it lands. What
must not happen is this file drifting: if Module 8 changes any of the three,
this changes with it.

Failure behaviour
-----------------
Every function returns rather than raises. Module 4 hangs off Module 3's
analyze endpoint, and an unreachable database must not take engagement
detection down with it - that is a working feature and this one is new. The
caller checks the return value and stays silent when a write fails, which is
the safe direction: no stored event means no intervention offered, rather than
an intervention the server cannot later recognise.
"""

import logging

from app.core.db import db

log = logging.getLogger(__name__)

# Must match app/analytics/persistence/collections.py:INTERVENTION_EVENTS.
COLLECTION = "analytics_intervention_events"

# Must match app/analytics/persistence/field_allowlists.py:INTERVENTION_EVENT_FIELDS.
# The contract sets additionalProperties: false and Module 8 filters on write,
# so anything outside this set is dropped twice over. Filtering here as well is
# what makes the documents identical either way.
ALLOWED_FIELDS = {
    "schema_version",
    "intervention_id",
    "session_id",
    "user_id",
    "content_id",
    "chunk_id",
    "timestamp",
    "intervention_type",
    "reason",
    "reason_code",
    "triggering_engagement_state",
    "triggering_engagement_event_id",
    "delivery_status",
    "outcome",
    "recovery_timestamp",
    "recovery_duration_seconds",
    "helped",
    "policy_version",
    "model_version",
}


def _filtered(event: dict) -> dict:
    return {k: v for k, v in event.items() if k in ALLOWED_FIELDS}


def save(event: dict) -> bool:
    """
    Write one event, replacing any previous version of it.

    Returns whether it was stored. `_id` is the intervention id, so a lifecycle
    transition overwrites the same document instead of accumulating one row per
    status - Module 8 reads a single document per intervention and takes its
    `timestamp` as the recovery anchor.
    """
    document = _filtered(dict(event))
    document["_id"] = event["intervention_id"]
    try:
        db[COLLECTION].replace_one({"_id": document["_id"]}, document, upsert=True)
        return True
    except Exception:
        # Deliberately broad: pymongo raises a wide family here, and every one
        # of them means the same thing to the caller. Logged with the id so a
        # missing intervention can be traced, and without the event body, which
        # carries a learner-facing reason string.
        log.warning("intervention %s could not be stored", document["_id"], exc_info=True)
        return False


def get(intervention_id: str) -> dict | None:
    try:
        document = db[COLLECTION].find_one({"_id": intervention_id})
    except Exception:
        log.warning("intervention %s could not be read", intervention_id, exc_info=True)
        return None
    if document is None:
        return None
    document = dict(document)
    document.pop("_id", None)
    return document


def list_for_session(session_id: str) -> list:
    """This session's interventions, oldest first."""
    try:
        cursor = db[COLLECTION].find({"session_id": session_id}).sort("timestamp", 1)
    except Exception:
        log.warning("interventions for session %s could not be read", session_id, exc_info=True)
        return []
    out = []
    for document in cursor:
        document = dict(document)
        document.pop("_id", None)
        out.append(document)
    return out

"""
The live path: engagement window in, intervention out, delivery reported back.

Where the trigger runs, and why it is not an endpoint the browser calls
----------------------------------------------------------------------
`evaluate` is called from inside Module 3's /engagement/analyze handler rather
than from a second request the client makes with the engagement event.

The deciding input is `raw_struggling` and `brow_struggling`. Both are
diagnostics: they are not in the engagement contract, and scope 6.8 says a
learner sees no scores or indicators during a session. Sending them to the
browser so it could send them back would mean the server trusting a client to
report how badly it was struggling, which is a trigger anyone can fabricate.
They stay on the server, so the decision does too.

The cost is one import pointing from Module 3 to Module 4 - a producer
notifying a consumer, which is the normal direction for this. Module 3 gains
one call and knows nothing about tiers, cooldowns or intervention types.

Failures here never propagate
-----------------------------
Engagement detection works today and interventions are new, so nothing in this
module is allowed to take that endpoint down. `evaluate` returns None on any
failure and reports why in the response's diagnostics, so a silent failure is
still a visible one in development.
"""

import logging

from app.intervention import content, contracts, cooldown, store
from app.intervention.decider import Signals
from app.intervention.policy import DefaultPolicy

log = logging.getLogger(__name__)

# The one place the decider is chosen.
#
# Scope 6.6 gives Module 6 the job of deciding which support is most likely to
# help and of planning sequences. When that lands it registers here and nothing
# else in the delivery path changes - which is the entire reason decide() sits
# behind an interface rather than being a function in this file.
_decider = DefaultPolicy()

# Dwell arrives from the browser, so it is bounded rather than trusted. An hour
# on one chunk is already past anything the gates distinguish.
MAX_DWELL_SECONDS = 3600.0

_model_version = None


def get_decider():
    return _decider


def set_decider(decider) -> None:
    """Swap the policy. Module 6's entry point, and how tests inject a stub."""
    global _decider
    _decider = decider


def model_version() -> str:
    """
    Which model produced the trigger, as filename plus a short content hash.

    MANIFEST.json records no version string, so the hash is the only thing that
    actually changes when the artifact does. Read once - hashing the model on
    every event would be wasteful, and this does not change while the process
    is running.
    """
    global _model_version
    if _model_version is None:
        try:
            from ml.inference import model as ml_model

            manifest = ml_model.load_manifest()
            digest = manifest["artifacts"][ml_model.MODEL_FILE]["sha256"]
            _model_version = f"{ml_model.MODEL_FILE}@{digest[:12]}"
        except Exception:
            log.warning("model version could not be read from the manifest", exc_info=True)
            _model_version = "unknown"
    return _model_version


def evaluate(
    uid: str,
    session_id: str,
    *,
    state: str,
    source: str,
    confidence: float,
    raw_struggling: bool,
    brow_struggling: bool,
    content_id: str = None,
    chunk_id: str = None,
    dwell_seconds: float = 0.0,
    engagement_event_id: str = None,
) -> dict:
    """
    Decide whether this window earns an intervention, and record it if so.

    Returns {"intervention": payload_or_None, "note": str}. The note is for the
    analyze response's diagnostics: "why did nothing happen" is the question
    this path will be asked most often, and the answer should not require
    reading the log.

    The event is stored BEFORE it is offered. If the write fails nothing is
    offered, because an intervention the server has no record of is one the
    browser could not report delivery for - and an event stuck at `offered`
    contributes to no metric Module 8 computes.
    """
    if cooldown.is_cooling(uid, session_id):
        return {"intervention": None, "note": "cooling down"}

    signals = Signals(
        state=state,
        source=source,
        # Module 3's own value. On develop this describes the model's argmax
        # class, which is not always `state` - the fix for that is in PR #44.
        # Passed through rather than recomputed here, and DefaultPolicy does
        # not read it, so nothing in this module depends on which it is.
        confidence=confidence,
        raw_struggling=raw_struggling,
        brow_struggling=brow_struggling,
        chunk_id=chunk_id,
        content_id=content_id,
        # Read from the stored chunk, never from the request. In P2 this
        # arrived from the browser because there was nowhere else to get it,
        # which let a client lower its own intervention thresholds by claiming
        # a section was critical. `is_critical` is already a field on a chunk
        # in Module 2's contract, so the day Module 9 starts writing it this
        # starts honouring it with no change here.
        is_critical=content.is_critical(uid, content_id, chunk_id),
        dwell_seconds=max(0.0, min(float(dwell_seconds or 0.0), MAX_DWELL_SECONDS)),
        engagement_event_id=engagement_event_id,
    )

    history = store.list_for_session(session_id)
    decision = _decider.decide(signals, history=history, recovery=None)
    if decision is None:
        return {"intervention": None, "note": "no intervention warranted"}

    event = contracts.build_intervention_event(
        decision=decision,
        user_id=uid,
        session_id=session_id,
        triggering_engagement_state=state,
        policy_version=getattr(_decider, "policy_version", None),
        model_version=model_version(),
    )

    if not store.save(event):
        return {"intervention": None, "note": "intervention could not be stored"}

    # Started on the offer rather than on delivery. If it started only once the
    # browser confirmed display, a client that is slow to report - or one that
    # never reports at all - would keep qualifying for a new intervention every
    # window. A failed delivery releases it again, see update_status.
    cooldown.record_fired(uid, session_id)

    return {
        "intervention": client_payload(event),
        "note": f"{decision.intervention_type} offered",
    }


def client_payload(event: dict) -> dict:
    """
    What the browser is given.

    Not the stored event. That carries user_id, policy_version, model_version
    and the outcome fields, which the browser has no use for. It also carries
    nothing about `tier` - how much the decider trusted itself - because scope
    6.8 puts scores and indicators out of reach during an active session, and a
    confidence tier is one however it is labelled. `reason` is learner-facing
    text and is meant to be shown.
    """
    return {
        "intervention_id": event["intervention_id"],
        "intervention_type": event["intervention_type"],
        "reason": event["reason"],
        "reason_code": event["reason_code"],
        "chunk_id": event.get("chunk_id"),
        "content_id": event.get("content_id"),
    }


def update_status(uid: str, session_id: str, intervention_id: str, delivery_status: str) -> dict:
    """
    Move an intervention along its lifecycle.

    Raises LookupError if it does not exist or belongs to someone else,
    contracts.InvalidTransition for a move the lifecycle does not allow, and
    ValueError for a status that is not a status at all.

    Repeating the current status is a no-op rather than an error: delivery
    reports come from a browser over an unreliable connection, and a client
    that retries after a dropped response is behaving correctly.
    """
    if delivery_status not in contracts.DELIVERY_STATUSES:
        raise ValueError(f"unknown delivery_status: {delivery_status}")

    event = store.get(intervention_id)
    # Same answer for "does not exist" and "is not yours", so this cannot be
    # used to find out which intervention ids are real.
    if event is None or event.get("user_id") != uid or event.get("session_id") != session_id:
        raise LookupError(intervention_id)

    if event["delivery_status"] == delivery_status:
        return event

    updated = contracts.advance(event, delivery_status)

    if not store.save(updated):
        raise RuntimeError("delivery status could not be stored")

    # A failed delivery never reached the learner, so the quiet period it
    # bought was spent on nothing. Releasing it stops a broken renderer from
    # silently starving somebody of support for two minutes at a time.
    # Dismissal is different: they saw it and said no, and asking again
    # immediately is the behaviour cooldown exists to prevent.
    if delivery_status == contracts.STATUS_FAILED:
        cooldown.reset(uid, session_id)

    return updated


def on_session_end(uid: str, session_id: str) -> None:
    """
    Release this session's in-memory state.

    Only cooldown lives in memory; the events themselves are in MongoDB and
    stay there. Calling this is not required for correctness - cooldown evicts
    a session after its own TTL - but a learner who starts a fresh session
    should not inherit the previous one's quiet period.
    """
    cooldown.reset(uid, session_id)

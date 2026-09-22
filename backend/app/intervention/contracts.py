"""
Boundary conversion from a Decision to intervention-event.schema.json shape.

Same arrangement as every other module's contracts.py: the shared contract
defines what modules send each other, not how this one works internally. A
Decision is internal; an intervention event is the exchange format.

Two things worth knowing before changing this file
--------------------------------------------------
The contract sets `additionalProperties: false`, and Module 8's
`INTERVENTION_EVENT_FIELDS` allowlist mirrors it exactly. So an extra field is
rejected twice: the schema refuses it and persistence silently drops it. That
is deliberate - it is what stops a stray blob being stored - so do not add a
field here without adding it to both.

`delivery_status` is not decorative. Module 8 only starts measuring recovery
from certain statuses, and they differ by intervention type:

    automatic    (simplify_content, bullet_summary)
                 displayed | accepted | completed
    learner      (break_suggestion, assistant_help_prompt, other)
                 accepted | completed

`offered` is in neither list, and that is correct - an intervention offered but
never displayed never reached the learner. An event left at `offered` is
invisible to every recovery metric, so the lifecycle has to be advanced as
delivery actually happens rather than fired once and forgotten.
"""

import uuid
from datetime import datetime, timezone

from app.intervention.decider import Decision

SCHEMA_VERSION = "1.0"

# Lifecycle, in the order it happens.
STATUS_OFFERED = "offered"
STATUS_DISPLAYED = "displayed"
STATUS_ACCEPTED = "accepted"
STATUS_DISMISSED = "dismissed"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

DELIVERY_STATUSES = (
    STATUS_OFFERED,
    STATUS_DISPLAYED,
    STATUS_ACCEPTED,
    STATUS_DISMISSED,
    STATUS_COMPLETED,
    STATUS_FAILED,
)

OUTCOME_NOT_OBSERVED = "not_observed"

# Mirrors Module 8's MetricConfig. Kept here so the lifecycle can be validated
# at the point events are built, rather than discovering months later that a
# whole intervention type never registered a recovery.
AUTOMATIC_TYPES = ("simplify_content", "bullet_summary")
LEARNER_INITIATED_TYPES = ("break_suggestion", "assistant_help_prompt", "other")

RECOVERY_ELIGIBLE = {
    **{t: ("displayed", "accepted", "completed") for t in AUTOMATIC_TYPES},
    **{t: ("accepted", "completed") for t in LEARNER_INITIATED_TYPES},
}


def starts_recovery_measurement(intervention_type: str, delivery_status: str) -> bool:
    """
    Whether Module 8 would begin measuring recovery from this state.

    Exposed so the executor and its tests can assert that a delivery path
    actually reaches a measurable status, instead of quietly producing events
    that contribute nothing.
    """
    return delivery_status in RECOVERY_ELIGIBLE.get(intervention_type, ())


def build_intervention_event(
    *,
    decision: Decision,
    user_id: str,
    session_id: str,
    triggering_engagement_state: str,
    delivery_status: str = STATUS_OFFERED,
    policy_version: str = None,
    model_version: str = None,
    intervention_id: str = None,
    timestamp: str = None,
) -> dict:
    """
    One intervention event, in contract shape.

    `outcome` starts at "not_observed" and `helped` at None. Both are filled in
    later by whatever measures recovery - post-session today, and mid-session
    once issue #45 lands. Setting either optimistically here would mean
    claiming an effect nobody has looked for.
    """
    if delivery_status not in DELIVERY_STATUSES:
        raise ValueError(f"unknown delivery_status: {delivery_status}")

    event = {
        "schema_version": SCHEMA_VERSION,
        "intervention_id": intervention_id or str(uuid.uuid4()),
        "session_id": session_id,
        "user_id": user_id,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "intervention_type": decision.intervention_type,
        "reason": decision.reason,
        "reason_code": decision.reason_code,
        "triggering_engagement_state": triggering_engagement_state,
        "delivery_status": delivery_status,
        "outcome": OUTCOME_NOT_OBSERVED,
        "helped": None,
    }

    # Optional fields are omitted rather than sent as null where the contract
    # allows absence, to keep stored events small and readable.
    if decision.content_id:
        event["content_id"] = decision.content_id
    if decision.chunk_id:
        event["chunk_id"] = str(decision.chunk_id)
    if decision.triggering_engagement_event_id:
        event["triggering_engagement_event_id"] = decision.triggering_engagement_event_id
    if policy_version:
        event["policy_version"] = policy_version
    if model_version:
        event["model_version"] = model_version

    # decision.sequence_id / step_index are deliberately NOT emitted. The
    # contract does not accept them yet (issue #45) and additionalProperties
    # is false, so sending them would fail validation. Add here when the
    # schema and Module 8's allowlist both accept them.

    return event


def advance(event: dict, delivery_status: str, *, timestamp: str = None) -> dict:
    """
    Return a copy of `event` moved to a new lifecycle status.

    A copy rather than a mutation because Module 8 keys writes on `event_id`
    and expects an idempotent record; mutating in place makes it ambiguous
    which version was persisted.
    """
    if delivery_status not in DELIVERY_STATUSES:
        raise ValueError(f"unknown delivery_status: {delivery_status}")
    updated = dict(event)
    updated["delivery_status"] = delivery_status
    updated["timestamp"] = timestamp or datetime.now(timezone.utc).isoformat()
    return updated

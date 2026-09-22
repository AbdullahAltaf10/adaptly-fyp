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
OUTCOME_DISMISSED = "dismissed"

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


# The legal moves through the lifecycle.
#
# This exists because delivery is reported by the browser, which makes it an
# untrusted input. Without a graph a caller could post "completed" against a
# freshly offered intervention and manufacture a recovery measurement for
# something that was never rendered. Repeating the current status is handled a
# level up as a no-op, so a client retrying after a dropped response does not
# get an error.
ALLOWED_TRANSITIONS = {
    STATUS_OFFERED: (STATUS_DISPLAYED, STATUS_FAILED),
    STATUS_DISPLAYED: (STATUS_ACCEPTED, STATUS_DISMISSED, STATUS_COMPLETED, STATUS_FAILED),
    STATUS_ACCEPTED: (STATUS_COMPLETED, STATUS_DISMISSED, STATUS_FAILED),
    STATUS_DISMISSED: (),
    STATUS_COMPLETED: (),
    STATUS_FAILED: (),
}

TERMINAL_STATUSES = (STATUS_DISMISSED, STATUS_COMPLETED, STATUS_FAILED)


class InvalidTransition(ValueError):
    """A delivery report that does not follow the lifecycle."""


def can_advance(current: str, proposed: str) -> bool:
    return proposed in ALLOWED_TRANSITIONS.get(current, ())


def is_anchored(event: dict) -> bool:
    """
    Whether this event's timestamp has already become a recovery anchor.

    See `advance` for why that matters.
    """
    return starts_recovery_measurement(
        event.get("intervention_type", ""), event.get("delivery_status", "")
    )


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

    A copy rather than a mutation because Module 8 keys writes on the
    intervention id and expects an idempotent record; mutating in place makes
    it ambiguous which version was persisted.

    The timestamp stops moving once it becomes a recovery anchor
    ------------------------------------------------------------
    There is one stored document per intervention, and Module 8's
    `_recovery_start_time` reads a single field from it - `timestamp` - and
    treats that as the moment the intervention reached the learner. It only
    does so when `delivery_status` is recovery-eligible for that type.

    So refreshing the timestamp on every transition would be wrong in a way
    that produces no error anywhere. An intervention going
    displayed -> accepted -> completed would end up stored with its completion
    time, and recovery would be measured from a window that starts minutes
    after the learner actually saw anything. The number would look plausible
    and mean nothing.

    The timestamp therefore advances while the event is not yet
    recovery-eligible and freezes at the first status that is. For an automatic
    type that is `displayed`; for a learner-initiated one `displayed` is not
    eligible, so it keeps moving until `accepted`. That falls out of
    RECOVERY_ELIGIBLE rather than being a second copy of the same rule.
    """
    if delivery_status not in DELIVERY_STATUSES:
        raise ValueError(f"unknown delivery_status: {delivery_status}")

    current = event.get("delivery_status")
    if not can_advance(current, delivery_status):
        raise InvalidTransition(f"cannot go from {current} to {delivery_status}")

    updated = dict(event)
    if not is_anchored(event):
        updated["timestamp"] = timestamp or datetime.now(timezone.utc).isoformat()
    updated["delivery_status"] = delivery_status

    # A dismissal is a delivery fact, not a judgement about whether the
    # intervention would have worked, so it is safe to record here while
    # `helped` stays None. Module 8 classifies outcome "dismissed" as unknown
    # rather than ineffective, which is the honest reading.
    if delivery_status == STATUS_DISMISSED:
        updated["outcome"] = OUTCOME_DISMISSED

    return updated

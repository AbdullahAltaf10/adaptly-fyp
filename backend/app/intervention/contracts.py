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

`delivered_at` is what Module 8 measures from, and this module is the only
thing that sets it. It is written once, at the moment the intervention reaches
the learner, and never moves again. If it is never set, the intervention is
invisible to every recovery metric - so the delivery lifecycle is not
bookkeeping, it is the whole measurement.

Which status counts as "reached the learner" differs by intervention type:

    automatic    (simplify_content, bullet_summary)
                 displayed | accepted | completed
    learner      (break_suggestion, assistant_help_prompt, other)
                 accepted | completed

`offered` is in neither list, and that is correct - an intervention offered but
never displayed never reached the learner. An event left at `offered` never
gets a `delivered_at`, so the lifecycle has to be advanced as delivery actually
happens rather than fired once and forgotten.
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


def is_delivered(event: dict) -> bool:
    """Whether delivery has already been recorded, and so must not move."""
    return bool(event.get("delivered_at"))


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

    # Carried when a decider sets them. Nothing does yet - sequencing belongs
    # to Module 6 - but the contract accepts them as of #54, so a sequencing
    # decider needs no change here.
    if decision.sequence_id:
        event["sequence_id"] = decision.sequence_id
    if decision.step_index is not None:
        event["step_index"] = decision.step_index

    # `delivered_at` is deliberately absent on a new event. It is set by
    # advance(), once, when delivery actually happens.

    return event


def advance(event: dict, delivery_status: str, *, timestamp: str = None) -> dict:
    """
    Return a copy of `event` moved to a new lifecycle status.

    A copy rather than a mutation because Module 8 keys writes on the
    intervention id and expects an idempotent record; mutating in place makes
    it ambiguous which version was persisted.

    `delivered_at` is written once and never moves
    ----------------------------------------------
    Module 8's `_recovery_start_time` reads exactly one field to decide when to
    start measuring: `delivered_at`. There is no fallback - an intervention
    without it is not measured at all - so setting it is this module's job and
    nobody else's.

    It is written at the first status that counts as reaching the learner for
    that intervention type, which comes straight out of RECOVERY_ELIGIBLE
    rather than being a second copy of the same rule. For an automatic type
    that is `displayed`; for a learner-initiated one `displayed` is not enough,
    so it waits for `accepted`.

    Once set it is never rewritten, including by a repeated status report from
    a retrying client. That is the whole point of the field: it is the one
    fixed fact in a lifecycle that keeps moving. `delivery_status` carries on
    to `dismissed` or `completed` afterwards without disturbing it, which is
    what #46 was about - an intervention that helped and was later dismissed
    used to lose its measurement entirely.

    `timestamp` stays where it was put: the moment the intervention was
    offered. It used to be dragged along as a stand-in anchor, which is what
    made detect-to-deliver latency impossible to compute. That workaround is
    gone.
    """
    if delivery_status not in DELIVERY_STATUSES:
        raise ValueError(f"unknown delivery_status: {delivery_status}")

    current = event.get("delivery_status")
    if not can_advance(current, delivery_status):
        raise InvalidTransition(f"cannot go from {current} to {delivery_status}")

    updated = dict(event)
    updated["delivery_status"] = delivery_status

    if not is_delivered(updated) and starts_recovery_measurement(
        updated.get("intervention_type", ""), delivery_status
    ):
        updated["delivered_at"] = timestamp or datetime.now(timezone.utc).isoformat()

    # A dismissal is a delivery fact, not a judgement about whether the
    # intervention would have worked, so it is safe to record here while
    # `helped` stays None. Module 8 classifies outcome "dismissed" as unknown
    # rather than ineffective, which is the honest reading.
    if delivery_status == STATUS_DISMISSED:
        updated["outcome"] = OUTCOME_DISMISSED

    return updated

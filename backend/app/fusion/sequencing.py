"""
Decision.sequence_id / step_index bookkeeping (scope 6.6's "plans responses
in sequences rather than single isolated actions").

The ladder order mirrors DefaultPolicy's own tiers (policy.py), cheapest
first: assistant_help_prompt -> bullet_summary -> simplify_content. This is
NOT new escalation logic invented here - it is the same order DefaultPolicy
already uses to choose a type in the first place, now also used to choose
the NEXT type when the current one is about to repeat without the learner
having recovered. DefaultPolicy could not do this itself (policy.py's own
docstring: "it does not escalate... a fake escalation that never checks
whether the previous step worked would be worse than none") - recovery
only became checkable mid-session in Task 1/2 (issue #45).
"""

import uuid

from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    BULLET_SUMMARY,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    TIER_STRONG,
    Decision,
)

_LADDER = (ASSISTANT_HELP_PROMPT, BULLET_SUMMARY, SIMPLIFY_CONTENT)

# Mirrors DefaultPolicy's own tier-per-type convention (policy.py) - escalating
# INTO a type must carry the tier that type would have if DefaultPolicy had
# chosen it directly, not the tier of whatever type preceded it.
_TIER_BY_TYPE = {
    ASSISTANT_HELP_PROMPT: TIER_BROAD,
    BULLET_SUMMARY: TIER_BROAD,
    SIMPLIFY_CONTENT: TIER_STRONG,
}

_REASON_BY_TYPE = {
    ASSISTANT_HELP_PROMPT: "The previous step didn't seem to help, so the assistant was offered again.",
    BULLET_SUMMARY: "The previous step didn't seem to help, so here are the key points instead.",
    SIMPLIFY_CONTENT: "The previous step didn't seem to help, so this section was simplified.",
}


def _next_rung(intervention_type: str, discouraged_types: frozenset) -> str:
    """The next rung up the ladder from `intervention_type`, skipping any
    rung in `discouraged_types` - preferences.py's own rule is that a
    learner's history can only make support gentler, never pushier, and
    escalating INTO a type they already told the system did not help them
    would do exactly that. Holds at the current type (does not escalate
    at all) if every rung above it is discouraged."""
    try:
        index = _LADDER.index(intervention_type)
    except ValueError:
        return intervention_type
    for candidate in _LADDER[index + 1:]:
        if candidate not in discouraged_types:
            return candidate
    return intervention_type


def _last_entry(history: list) -> dict | None:
    return history[-1] if history else None


def next_sequence(
    base_decision: Decision,
    *,
    history: list,
    recovery_since_last_decision: bool | None,
    discouraged_types: frozenset = frozenset(),
) -> Decision:
    """Return `base_decision` with sequence_id/step_index filled in -
    escalated one rung, continuing the previous sequence, if the same
    type would otherwise repeat without a genuine recovery in between.
    Starts a fresh sequence in every other case (no history, recovery was
    True, recovery is unknown/None, or this is already a different type
    than last time)."""
    last = _last_entry(history)
    last_type = last.get("intervention_type") if last else None
    should_escalate = (
        recovery_since_last_decision is False
        and last is not None
        and last_type == base_decision.intervention_type
    )

    if not should_escalate:
        return Decision(
            intervention_type=base_decision.intervention_type,
            reason_code=base_decision.reason_code,
            reason=base_decision.reason,
            tier=base_decision.tier,
            chunk_id=base_decision.chunk_id,
            content_id=base_decision.content_id,
            triggering_engagement_event_id=base_decision.triggering_engagement_event_id,
            sequence_id=str(uuid.uuid4()),
            step_index=0,
        )

    escalated_type = _next_rung(base_decision.intervention_type, discouraged_types)
    # Escalating changes what is being offered, so a reason/tier written for
    # the PREVIOUS type must not ride along unchanged - stale text like
    # "...offered the assistant" surviving onto a bullet_summary Decision is
    # wrong on its face, and actively misleading when it was itself a
    # _because_of_history() sentence naming a different type. Held-in-place
    # (every higher rung discouraged) keeps the original reason/tier, since
    # nothing about the offer actually changed.
    reason = base_decision.reason
    tier = base_decision.tier
    if escalated_type != base_decision.intervention_type:
        reason = _REASON_BY_TYPE.get(escalated_type, base_decision.reason)
        tier = _TIER_BY_TYPE.get(escalated_type, base_decision.tier)

    # A last entry can come from DefaultPolicy (never writes sequence_id -
    # contracts.py only accepts it once Module 6 produced it), e.g. the
    # first evaluate() after ADAPTLY_FUSION_POLICY is turned on mid-session.
    # Treat a missing/falsy sequence_id as "nothing to continue" - a fresh
    # sequence, starting at step 0, not a KeyError and not a step_index
    # that implies a continuation that was never actually recorded.
    previous_sequence_id = last.get("sequence_id")
    if previous_sequence_id:
        sequence_id = previous_sequence_id
        step_index = (last.get("step_index") or 0) + 1
    else:
        sequence_id = str(uuid.uuid4())
        step_index = 0

    return Decision(
        intervention_type=escalated_type,
        reason_code=base_decision.reason_code,
        reason=reason,
        tier=tier,
        chunk_id=base_decision.chunk_id,
        content_id=base_decision.content_id,
        triggering_engagement_event_id=base_decision.triggering_engagement_event_id,
        sequence_id=sequence_id,
        step_index=step_index,
    )

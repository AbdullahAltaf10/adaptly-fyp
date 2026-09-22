"""
Module 4 P1 — the decision logic.

No database, no model load, no clock. The policy is a pure function and the
cooldown takes an injectable `now`, so none of this sleeps or needs fixtures.

What these pin, and why each matters
------------------------------------
The tiers come from measurement (ml/evaluation/trigger_fusion.py), so the
tests assert the measured shape rather than an arbitrary one: STRONG gates the
intrusive responses, BROAD gates the gentle ones.

The lifecycle assertions exist because Module 8 only measures recovery from
particular statuses, and they differ by intervention type. Getting that wrong
produces events that look fine and contribute nothing to any metric - a
failure that would otherwise surface months later as an empty dashboard.
"""

import pytest

from app.intervention import contracts, cooldown
from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    BREAK_SUGGESTION,
    BULLET_SUMMARY,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    TIER_RULE,
    TIER_STRONG,
    Decision,
    Signals,
)
from app.intervention.policy import DefaultPolicy


def signals(**overrides):
    base = dict(
        state="struggling",
        source="lstm",
        confidence=0.4,
        raw_struggling=False,
        brow_struggling=False,
        chunk_id="3",
        content_id="c1",
        is_critical=False,
        dwell_seconds=0.0,
        engagement_event_id="e1",
    )
    base.update(overrides)
    return Signals(**base)


# --------------------------------------------------------------------------
# Staying silent
# --------------------------------------------------------------------------

def test_says_nothing_when_neither_signal_fires():
    """The common case. A policy that fires on focus would be unusable."""
    assert DefaultPolicy().decide(signals(state="focused")) is None


def test_says_nothing_when_state_is_struggling_but_no_signal_supports_it():
    """
    `state` alone is not evidence.

    The reported state can be struggling while the raw class and the brow rule
    both disagree - smoothing holds a previous state through transitions. The
    tiers are built from the signals, not from the label.
    """
    assert DefaultPolicy().decide(signals(raw_struggling=False, brow_struggling=False)) is None


# --------------------------------------------------------------------------
# The tiers, as measured
# --------------------------------------------------------------------------

def test_strong_plus_long_dwell_gives_the_most_intrusive_response():
    """AND of both signals measured at 1.82x lift - the strongest available."""
    decision = DefaultPolicy().decide(
        signals(raw_struggling=True, brow_struggling=True, dwell_seconds=60.0)
    )
    assert decision.intervention_type == SIMPLIFY_CONTENT
    assert decision.tier == TIER_STRONG


def test_strong_but_short_dwell_falls_back_to_a_summary():
    """
    Rewriting a section somebody has barely looked at is not justified, however
    strong the engagement signal.
    """
    decision = DefaultPolicy().decide(
        signals(raw_struggling=True, brow_struggling=True, dwell_seconds=20.0)
    )
    assert decision.intervention_type == BULLET_SUMMARY


def test_one_signal_only_never_rewrites_content():
    """
    BROAD measured at 1.20x against STRONG's 1.82x. The weaker tier must not
    reach the most intrusive response no matter how long the dwell.
    """
    decision = DefaultPolicy().decide(
        signals(raw_struggling=True, brow_struggling=False, dwell_seconds=600.0)
    )
    assert decision.intervention_type == BULLET_SUMMARY
    assert decision.tier == TIER_BROAD


def test_brow_signal_alone_still_counts():
    """
    The per-user rule reaches 12 of 19 subjects against the model's 9, so it
    must be able to trigger on its own.
    """
    decision = DefaultPolicy().decide(
        signals(raw_struggling=False, brow_struggling=True, dwell_seconds=20.0)
    )
    assert decision is not None
    assert decision.intervention_type == BULLET_SUMMARY


def test_no_dwell_gives_the_cheapest_response():
    """With no dwell signal at all, only the free response is justified."""
    decision = DefaultPolicy().decide(
        signals(raw_struggling=True, brow_struggling=True, dwell_seconds=0.0)
    )
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT


# --------------------------------------------------------------------------
# Fatigue sits outside the tiers
# --------------------------------------------------------------------------

def test_fatigue_fires_without_needing_the_model_to_agree():
    """
    `fatigued` is a rule state carrying its own evidence (fatigue_ratio), so it
    does not need corroboration from a model that was not consulted about
    fatigue at all.
    """
    decision = DefaultPolicy().decide(
        signals(state="fatigued", raw_struggling=False, brow_struggling=False)
    )
    assert decision.intervention_type == BREAK_SUGGESTION
    assert decision.tier == TIER_RULE


# --------------------------------------------------------------------------
# Critical sections - scope 6.9
# --------------------------------------------------------------------------

def test_critical_chunks_lower_both_gates():
    policy = DefaultPolicy()
    normal = policy.gates_for(signals())
    critical = policy.gates_for(signals(is_critical=True))
    assert critical[0] < normal[0]
    assert critical[1] < normal[1]


def test_critical_chunk_reaches_simplify_on_a_dwell_that_would_not_otherwise():
    """
    Scope 6.9: "respond earlier where comprehension matters most."
    30s is below the normal 45s gate but above the halved critical one.
    """
    policy = DefaultPolicy()
    common = dict(raw_struggling=True, brow_struggling=True, dwell_seconds=30.0)
    assert policy.decide(signals(**common)).intervention_type == BULLET_SUMMARY
    assert policy.decide(signals(is_critical=True, **common)).intervention_type == SIMPLIFY_CONTENT


def test_thresholds_are_parameters_not_constants():
    """
    Module 9 will need to tune these per chunk. A policy with baked-in
    constants would force a signature change then.
    """
    strict = DefaultPolicy(dwell_long=600.0, dwell_short=300.0)
    decision = strict.decide(
        signals(raw_struggling=True, brow_struggling=True, dwell_seconds=60.0)
    )
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT


def test_nonsense_configuration_is_rejected_at_construction():
    with pytest.raises(ValueError):
        DefaultPolicy(dwell_long=10.0, dwell_short=30.0)
    with pytest.raises(ValueError):
        DefaultPolicy(critical_factor=0)


# --------------------------------------------------------------------------
# Decision validity
# --------------------------------------------------------------------------

def test_decision_rejects_values_the_contract_would_reject():
    """Fail at construction, not at the schema boundary."""
    with pytest.raises(ValueError):
        Decision(intervention_type="make_coffee", reason_code="struggling",
                 reason="x", tier=TIER_BROAD)
    with pytest.raises(ValueError):
        Decision(intervention_type=SIMPLIFY_CONTENT, reason_code="bored",
                 reason="x", tier=TIER_BROAD)


@pytest.mark.parametrize("raw,brow,dwell", [
    (True, True, 60.0), (True, True, 20.0), (True, False, 60.0),
    (False, True, 5.0), (True, True, 0.0),
])
def test_every_decision_carries_a_reason_and_valid_ids(raw, brow, dwell):
    """Module 8's dashboard shows "the reason for each one" - it cannot be blank."""
    decision = DefaultPolicy().decide(
        signals(raw_struggling=raw, brow_struggling=brow, dwell_seconds=dwell)
    )
    assert decision.reason.strip()
    assert decision.chunk_id == "3"
    assert decision.triggering_engagement_event_id == "e1"


# --------------------------------------------------------------------------
# Cooldown
# --------------------------------------------------------------------------

def test_cooldown_default_is_not_shorter_than_module_8s_recovery_window():
    """
    Module 8 measures recovery over 120s and has to cope with overlap via
    `competing_start`. Firing inside that window makes attribution ambiguous,
    which corrupts a number Module 10 turns into a compliance figure.
    """
    assert cooldown.DEFAULT_COOLDOWN_SECONDS >= 120.0


def test_cooldown_blocks_then_expires():
    cooldown.reset("u", "s")
    assert cooldown.is_cooling("u", "s", now=1000.0) is False
    cooldown.record_fired("u", "s", now=1000.0)
    assert cooldown.is_cooling("u", "s", now=1050.0) is True
    assert cooldown.is_cooling("u", "s", now=1121.0) is False
    cooldown.reset("u", "s")


def test_cooldown_is_per_session():
    cooldown.reset("u", "a")
    cooldown.reset("u", "b")
    cooldown.record_fired("u", "a", now=1000.0)
    assert cooldown.is_cooling("u", "a", now=1010.0) is True
    assert cooldown.is_cooling("u", "b", now=1010.0) is False
    cooldown.reset("u", "a")


# --------------------------------------------------------------------------
# The contract boundary, and the lifecycle Module 8 actually measures
# --------------------------------------------------------------------------

def test_offered_measures_nothing_for_any_type():
    """
    The mistake this pins: my first plan logged interventions at `offered` and
    stopped. Module 8 correctly ignores that status, so every one of those
    events would have contributed nothing to any recovery metric.
    """
    for intervention_type in contracts.AUTOMATIC_TYPES + contracts.LEARNER_INITIATED_TYPES:
        assert not contracts.starts_recovery_measurement(intervention_type, "offered")


def test_automatic_types_measure_from_displayed_but_learner_types_do_not():
    """
    A simplification is experienced once shown. A break suggestion is not
    experienced until accepted, so a fire-and-forget banner registers nothing.
    """
    assert contracts.starts_recovery_measurement(SIMPLIFY_CONTENT, "displayed")
    assert contracts.starts_recovery_measurement(BULLET_SUMMARY, "displayed")
    assert not contracts.starts_recovery_measurement(BREAK_SUGGESTION, "displayed")
    assert not contracts.starts_recovery_measurement(ASSISTANT_HELP_PROMPT, "displayed")
    assert contracts.starts_recovery_measurement(BREAK_SUGGESTION, "accepted")
    assert contracts.starts_recovery_measurement(ASSISTANT_HELP_PROMPT, "completed")


def test_event_has_exactly_the_fields_the_contract_allows():
    """
    `additionalProperties: false` on the schema, and Module 8's allowlist
    mirrors it. An extra field is rejected twice - once loudly, once silently.
    """
    allowed = {
        "schema_version", "intervention_id", "session_id", "user_id",
        "content_id", "chunk_id", "timestamp", "intervention_type", "reason",
        "reason_code", "triggering_engagement_state",
        "triggering_engagement_event_id", "delivery_status", "outcome",
        "recovery_timestamp", "recovery_duration_seconds", "helped",
        "policy_version", "model_version",
    }
    decision = DefaultPolicy().decide(
        signals(raw_struggling=True, brow_struggling=True, dwell_seconds=60.0)
    )
    event = contracts.build_intervention_event(
        decision=decision, user_id="u", session_id="s",
        triggering_engagement_state="struggling", policy_version="v1-tiered",
    )
    assert set(event) <= allowed, f"not in contract: {set(event) - allowed}"


def test_sequence_fields_are_not_emitted_until_the_contract_accepts_them():
    """
    Decision carries sequence_id/step_index for a future sequencing decider,
    but the contract does not have them yet (issue #45). Emitting them would
    fail validation.
    """
    decision = Decision(
        intervention_type=SIMPLIFY_CONTENT, reason_code="struggling",
        reason="x", tier=TIER_STRONG, sequence_id="seq-1", step_index=2,
    )
    event = contracts.build_intervention_event(
        decision=decision, user_id="u", session_id="s",
        triggering_engagement_state="struggling",
    )
    assert "sequence_id" not in event
    assert "step_index" not in event


def test_new_events_claim_no_outcome():
    """Setting outcome optimistically would claim an effect nobody looked for."""
    decision = DefaultPolicy().decide(signals(state="fatigued"))
    event = contracts.build_intervention_event(
        decision=decision, user_id="u", session_id="s",
        triggering_engagement_state="fatigued",
    )
    assert event["outcome"] == "not_observed"
    assert event["helped"] is None
    assert event["delivery_status"] == "offered"


def test_advance_copies_rather_than_mutates():
    """Module 8 keys writes on the id and expects an idempotent record."""
    decision = DefaultPolicy().decide(signals(state="fatigued"))
    event = contracts.build_intervention_event(
        decision=decision, user_id="u", session_id="s",
        triggering_engagement_state="fatigued",
    )
    moved = contracts.advance(event, "displayed")
    assert event["delivery_status"] == "offered"
    assert moved["delivery_status"] == "displayed"
    assert moved["intervention_id"] == event["intervention_id"]


def test_unknown_delivery_status_is_rejected():
    decision = DefaultPolicy().decide(signals(state="fatigued"))
    with pytest.raises(ValueError):
        contracts.build_intervention_event(
            decision=decision, user_id="u", session_id="s",
            triggering_engagement_state="fatigued", delivery_status="maybe",
        )

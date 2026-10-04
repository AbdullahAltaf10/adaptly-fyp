import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion.sequencing import next_sequence  # noqa: E402
from app.intervention.decider import (  # noqa: E402
    ASSISTANT_HELP_PROMPT,
    BULLET_SUMMARY,
    REASON_STRUGGLING,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    Decision,
)


def _decision(intervention_type: str) -> Decision:
    return Decision(
        intervention_type=intervention_type, reason_code=REASON_STRUGGLING,
        reason="test", tier=TIER_BROAD,
    )


def _history_entry(intervention_type: str, sequence_id: str | None = None, step_index: int | None = None):
    return {
        "intervention_type": intervention_type,
        "sequence_id": sequence_id,
        "step_index": step_index,
    }


def test_starts_a_fresh_sequence_when_there_is_no_history():
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=[], recovery_since_last_decision=None,
    )
    assert result.step_index == 0
    assert result.sequence_id is not None
    uuid.UUID(result.sequence_id)  # a real uuid4, not a placeholder string


def test_starts_a_fresh_sequence_after_genuine_recovery():
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=True,
    )
    assert result.sequence_id != "seq-1"
    assert result.step_index == 0


def test_escalates_when_the_same_type_would_repeat_without_recovery():
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=False,
    )
    assert result.sequence_id == "seq-1"
    assert result.step_index == 1
    assert result.intervention_type == BULLET_SUMMARY  # next rung up the ladder


def test_escalates_again_to_the_top_rung():
    history = [_history_entry(BULLET_SUMMARY, sequence_id="seq-1", step_index=1)]
    result = next_sequence(
        _decision(BULLET_SUMMARY), history=history, recovery_since_last_decision=False,
    )
    assert result.step_index == 2
    assert result.intervention_type == SIMPLIFY_CONTENT


def test_does_not_escalate_past_the_top_rung():
    history = [_history_entry(SIMPLIFY_CONTENT, sequence_id="seq-1", step_index=2)]
    result = next_sequence(
        _decision(SIMPLIFY_CONTENT), history=history, recovery_since_last_decision=False,
    )
    assert result.intervention_type == SIMPLIFY_CONTENT
    assert result.step_index == 3


def test_does_not_escalate_when_recovery_is_none():
    """Matches DefaultPolicy's own current, documented behavior: no
    escalation without a real recovery signal to escalate ON THE BASIS of -
    recovery=None is not the same as recovery=False."""
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=None,
    )
    assert result.sequence_id != "seq-1"
    assert result.step_index == 0


def test_does_not_escalate_when_the_base_decision_is_a_different_type():
    """Escalation only applies when the SAME type would repeat - a
    different type this time is already a different response, not a stall."""
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(BULLET_SUMMARY), history=history, recovery_since_last_decision=False,
    )
    assert result.sequence_id != "seq-1"
    assert result.step_index == 0


def test_tolerates_a_malformed_history_entry_missing_intervention_type():
    history = [{"sequence_id": "seq-1", "step_index": 0}]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=False,
    )
    assert result.step_index == 0  # treated as "no comparable prior entry"


def test_tolerates_a_history_entry_with_no_sequence_id_at_all():
    """A real, reachable case, not just a malformed-input defensive test:
    DefaultPolicy's own events never carry sequence_id (contracts.py only
    accepts it once Module 6 produced it) - so the very first time
    ADAPTLY_FUSION_POLICY is turned on mid-session, `history[-1]` is a
    DefaultPolicy-origin entry with no "sequence_id" key at all. Must start
    a fresh sequence, not KeyError on a bare `last["sequence_id"]` index."""
    history = [{"intervention_type": ASSISTANT_HELP_PROMPT, "step_index": 0}]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=False,
    )
    assert result.step_index == 0
    uuid.UUID(result.sequence_id)


def test_escalation_skips_a_discouraged_rung():
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=False,
        discouraged_types=frozenset({BULLET_SUMMARY}),
    )
    assert result.sequence_id == "seq-1"
    assert result.intervention_type == SIMPLIFY_CONTENT  # BULLET_SUMMARY skipped


def test_escalation_holds_at_the_current_type_when_every_rung_above_it_is_discouraged():
    """Preferences.py's own rule, which this module must not violate: a
    learner's history 'can only make support gentler, never pushier'.
    Escalating INTO a discouraged type would widen what is offered, which
    decider.py's own Signals.discouraged_types docstring forbids."""
    history = [_history_entry(BULLET_SUMMARY, sequence_id="seq-1", step_index=1)]
    result = next_sequence(
        _decision(BULLET_SUMMARY), history=history, recovery_since_last_decision=False,
        discouraged_types=frozenset({SIMPLIFY_CONTENT}),
    )
    assert result.intervention_type == BULLET_SUMMARY  # held, not escalated into SIMPLIFY_CONTENT


def test_reason_and_tier_are_regenerated_for_the_escalated_type_not_left_stale():
    """The bug this pins: escalating assistant_help_prompt -> bullet_summary
    while keeping the OLD reason text ("...offered the assistant.") and tier
    produces an event that says one thing and does another - wrong on its
    face, and actively misleading when the old reason text was itself a
    _because_of_history() sentence naming a *different* type."""
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    base = Decision(
        intervention_type=ASSISTANT_HELP_PROMPT, reason_code=REASON_STRUGGLING,
        reason="Signs of difficulty; offered the assistant.", tier=TIER_BROAD,
    )
    result = next_sequence(base, history=history, recovery_since_last_decision=False)
    assert result.intervention_type == BULLET_SUMMARY
    assert "assistant" not in result.reason.lower()
    assert "summary" in result.reason.lower() or "key points" in result.reason.lower()


def test_tier_escalates_to_strong_when_the_ladder_reaches_simplify_content():
    from app.intervention.decider import TIER_STRONG

    history = [_history_entry(BULLET_SUMMARY, sequence_id="seq-1", step_index=1)]
    base = Decision(
        intervention_type=BULLET_SUMMARY, reason_code=REASON_STRUGGLING,
        reason="Signs of difficulty on this section.", tier=TIER_BROAD,
    )
    result = next_sequence(base, history=history, recovery_since_last_decision=False)
    assert result.intervention_type == SIMPLIFY_CONTENT
    assert result.tier == TIER_STRONG

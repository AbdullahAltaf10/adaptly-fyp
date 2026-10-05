from app.intervention.decider import ASSISTANT_HELP_PROMPT, REASON_READING_DIFFICULTY, Signals
from app.intervention.policy import DefaultPolicy


def _signals(**overrides):
    base = dict(
        state="focused",
        source="lstm",
        confidence=0.9,
        raw_struggling=False,
        brow_struggling=False,
        dwell_seconds=0.0,
    )
    base.update(overrides)
    return Signals(**base)


def test_revisit_alone_triggers_the_assistant_prompt_with_reading_difficulty_reason():
    policy = DefaultPolicy()
    decision = policy.decide(_signals(paragraph_revisit_detected=True))
    assert decision is not None
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT
    assert decision.reason_code == REASON_READING_DIFFICULTY


def test_no_revisit_and_no_struggling_triggers_nothing():
    policy = DefaultPolicy()
    decision = policy.decide(_signals(paragraph_revisit_detected=False))
    assert decision is None


def test_struggling_evidence_still_wins_over_a_simultaneous_revisit():
    # The existing struggling path is checked first in this branch's parent
    # `if not broad` guard - a revisit alongside real struggling evidence
    # must not downgrade an already-earned stronger response.
    policy = DefaultPolicy()
    decision = policy.decide(
        _signals(state="struggling", raw_struggling=True, brow_struggling=True, dwell_seconds=999, paragraph_revisit_detected=True)
    )
    assert decision.reason_code != REASON_READING_DIFFICULTY


def test_discouraged_assistant_prompt_suppresses_the_revisit_trigger():
    policy = DefaultPolicy()
    decision = policy.decide(
        _signals(paragraph_revisit_detected=True, discouraged_types=frozenset({ASSISTANT_HELP_PROMPT}))
    )
    assert decision is None

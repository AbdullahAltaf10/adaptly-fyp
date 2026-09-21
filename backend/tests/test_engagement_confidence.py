"""
`confidence` must describe the state the event actually reports.

The bug these pin
-----------------
Every engagement event used to carry `prediction["confidence"]` - the model's
confidence in its own raw winning class - regardless of which layer decided
the state. Three cases where that is the wrong number:

  fatigued / recovered   the state comes from a rule, so the model's
                         confidence describes a different class entirely
  smoothing transition   the displayed state is deliberately held through a
                         transition, so it differs from the raw class

A `fatigued` event carrying the model's confidence in `focused` is not a
cosmetic problem: Module 8 persists this field, so the wrong value
accumulates, and anything later reading "state + confidence" as a pair reads
two unrelated things.

These tests exercise `contracts.confidence_for` and the contract meaning
directly rather than the endpoint, so they need no database, no Firebase and
no model load.
"""

import pytest

from app.engagement import contracts


def prediction(top_state, top_confidence, probabilities=None):
    """Shaped like ml.inference.model.predict()'s return value."""
    result = {"state": top_state, "confidence": top_confidence}
    if probabilities is not None:
        result["probabilities"] = probabilities
    return result


# --------------------------------------------------------------------------
# The core of the fix
# --------------------------------------------------------------------------

def test_reports_the_probability_of_the_state_being_reported():
    """
    The smoothing layer holds `focused` while the raw class is `struggling`.

    Before the fix this event said `state: focused, confidence: 0.71` - the
    0.71 belonging to struggling, the class deliberately not reported.
    """
    p = prediction("struggling", 0.71,
                   {"focused": 0.21, "drifting": 0.08, "struggling": 0.71})
    assert contracts.confidence_for(p, "focused") == pytest.approx(0.21)


def test_agrees_with_the_top_class_when_nothing_is_being_held():
    """The ordinary case must be unchanged."""
    p = prediction("focused", 0.64,
                   {"focused": 0.64, "drifting": 0.22, "struggling": 0.14})
    assert contracts.confidence_for(p, "focused") == pytest.approx(0.64)


def test_falls_back_when_per_class_probabilities_are_absent():
    """
    An older caller, or a stubbed model, still works.

    The fallback is the previous behaviour, so this can be introduced without
    changing every call site at once - but it is a fallback, not the intent.
    """
    p = prediction("drifting", 0.55)
    assert contracts.confidence_for(p, "drifting") == pytest.approx(0.55)
    assert contracts.confidence_for(p, "focused") == pytest.approx(0.55)


def test_falls_back_when_the_reported_state_is_not_a_model_class():
    """`fatigued` is a rule state and has no model probability."""
    p = prediction("focused", 0.80,
                   {"focused": 0.80, "drifting": 0.12, "struggling": 0.08})
    assert contracts.confidence_for(p, "fatigued") == pytest.approx(0.80)


# --------------------------------------------------------------------------
# The rule states
# --------------------------------------------------------------------------

def test_rule_certain_is_in_contract_range():
    """engagement-event.schema.json requires confidence in [0, 1]."""
    assert 0.0 <= contracts.RULE_CERTAIN <= 1.0


def test_fatigue_ratio_is_usable_as_a_confidence():
    """
    The value routes.py hands to a `fatigued` event.

    fatigue.py fires at a ratio of 0.80 and reports the measured ratio, so it
    is already in range and already describes fatigue rather than a model
    class. This pins that it stays in range if that threshold ever moves.
    """
    from app.engagement import fatigue

    assert 0.0 <= fatigue.MIN_LOW_RATIO <= 1.0


# --------------------------------------------------------------------------
# The event that comes out the other end
# --------------------------------------------------------------------------

def test_event_carries_the_confidence_it_was_given():
    """No rounding or substitution between the decision and the event."""
    event = contracts.build_engagement_event(
        user_id="u", session_id="s", state="fatigued",
        confidence=0.87, source=contracts.SOURCE_RULE,
    )
    assert event["state"] == "fatigued"
    assert event["confidence"] == pytest.approx(0.87)
    assert event["source"] == contracts.SOURCE_RULE


@pytest.mark.parametrize("state,source,confidence", [
    ("fatigued", contracts.SOURCE_RULE, 0.93),
    ("recovered", contracts.SOURCE_RULE, contracts.RULE_CERTAIN),
    ("focused", contracts.SOURCE_MODEL, 0.41),
    ("struggling", contracts.SOURCE_HYBRID, 0.38),
])
def test_every_source_produces_a_contract_valid_confidence(state, source, confidence):
    event = contracts.build_engagement_event(
        user_id="u", session_id="s", state=state,
        confidence=confidence, source=source,
    )
    assert 0.0 <= event["confidence"] <= 1.0
    assert event["state"] == state

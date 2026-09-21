"""
Boundary conversion to shared/contracts/engagement-event.schema.json.

Same arrangement as the other modules: the contract describes what leaves this
module, not how it works internally.

Two things this file exists to get right:

**The contract is strict.** `additionalProperties: false`, so the diagnostic
values the rules produce — confirmation streaks, fatigue ratios, stillness
variances, furrow ratios — cannot travel in an engagement event. They are
development instruments, not part of the exchange format, and are returned
separately in the API response.

**The five states are not all model output.** `focused`, `drifting` and
`struggling` come from the LSTM; `fatigued` and `recovered` come from rules,
because DAiSEE has no fatigue dimension and "recovered" is a comparison across
time that a single ten-second clip cannot express. The contract's `source`
field records which produced a given event, so nothing downstream has to guess.
"""

import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"

SOURCE_MODEL = "lstm"
SOURCE_RULE = "rule"
SOURCE_HYBRID = "hybrid"

# What `confidence` means in an engagement event
# ----------------------------------------------
# engagement-event.schema.json requires `confidence` and constrains it to a
# number in [0, 1], but says nothing about what it measures. Defining it here,
# because a field every module reads and nobody has defined is a field that
# will be read three different ways.
#
#   confidence describes THE STATE THE EVENT REPORTS, from whichever layer
#   produced that state.
#
#     source=lstm    the model's probability for the reported class
#     source=hybrid  same - Deep Thinking changes `source`, not the state
#     source=rule    the rule's own strength of evidence
#
# It is NOT "the model's confidence in its top class". That is what the code
# used to send regardless of which layer decided the state, which meant a
# `fatigued` event carried the model's confidence in `focused`.
#
# It is also not a calibrated probability. Module 3's model is measurably
# uncalibrated (see ml/evaluation/), so treat confidence as an ordering
# signal - useful for "more certain than that one" - and not as a percentage.

# For a deterministic rule that either fires or does not. Says the rule's
# condition was met, not that the underlying claim is certainly true.
RULE_CERTAIN = 1.0


def confidence_for(prediction: dict, reported_state: str) -> float:
    """
    The model's probability for `reported_state`, not for its own top class.

    These differ whenever the smoothing layer is holding a previous state
    through a transition, which is exactly what smoothing exists to do. Before
    this, such an event carried the confidence of the raw class it was
    deliberately NOT reporting.

    Falls back to the top-class confidence when per-class probabilities are
    unavailable - an older caller, or a stubbed model in a test - so this can
    be introduced without every call site changing at once.
    """
    probabilities = prediction.get("probabilities")
    if probabilities and reported_state in probabilities:
        return float(probabilities[reported_state])
    return float(prediction["confidence"])

# The 7 facial values the contract names, mapped from our internal feature order.
# brow_raise and inter_brow were added to the contract during the #7 review -
# without them the 9-feature model output could not be represented at all.
_FEATURE_TO_CONTRACT = {
    "gaze_x": "gaze_x",
    "gaze_y": "gaze_y",
    "blink_rate": "blink_rate",
    "pitch": "head_pitch",
    "yaw": "head_yaw",
    "roll": "head_roll",
    "eye_openness": "eye_openness",
    "brow_raise": "brow_raise",
    "inter_brow": "inter_brow",
}

FEATURE_ORDER = [
    "gaze_x", "gaze_y", "blink_rate", "pitch", "yaw",
    "roll", "eye_openness", "brow_raise", "inter_brow",
]


def build_engagement_event(
    *,
    user_id: str,
    session_id: str,
    state: str,
    confidence: float,
    source: str,
    features=None,
    content_id: str = None,
    chunk_id: str = None,
    deep_thinking_detected: bool = False,
    gaze_regression_detected: bool = False,
) -> dict:
    """
    One engagement event, in contract shape.

    `features` is the mean of the window's calibration-corrected features, or
    None. Included because Module 8 and any later evaluation need the underlying
    signal, not only the label.
    """
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "confidence": float(confidence),
        "deep_thinking_detected": bool(deep_thinking_detected),
        # False here means "not measured" - the OneStop classifier does not
        # exist. See engagement/rereading.py.
        "gaze_regression_detected": bool(gaze_regression_detected),
        "source": source,
    }

    if content_id:
        event["content_id"] = content_id
    if chunk_id:
        event["chunk_id"] = str(chunk_id)

    if features:
        for internal_name, value in zip(FEATURE_ORDER, features):
            contract_name = _FEATURE_TO_CONTRACT.get(internal_name)
            if contract_name:
                event[contract_name] = round(float(value), 6)

    return event


def mean_features(feature_sequence):
    """Average each feature across the window, for the event's facial values."""
    if not feature_sequence:
        return None
    count = len(feature_sequence)
    return [sum(frame[i] for frame in feature_sequence) / count
            for i in range(len(feature_sequence[0]))]

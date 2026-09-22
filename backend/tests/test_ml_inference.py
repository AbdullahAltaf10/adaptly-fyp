"""
Feature extraction, landmark validation, and a model loading/prediction smoke test.

Two acceptance criteria on the issue depend on this file:
"feature-extraction tests pass" and "model loading and prediction smoke test
passes".
"""

import math
import random

import pytest

from ml.inference import model as ml_model
from ml.inference.features import (
    EXPECTED_LANDMARK_COUNT,
    FEATURE_NAMES,
    InvalidLandmarksError,
    extract_features,
    validate_landmarks,
)


def make_landmarks(seed=0):
    """478 plausible face-shaped points in normalised coordinates."""
    rng = random.Random(seed)
    return [[0.5 + rng.uniform(-0.2, 0.2),
             0.5 + rng.uniform(-0.2, 0.2),
             rng.uniform(-0.05, 0.05)] for _ in range(EXPECTED_LANDMARK_COUNT)]


# --------------------------------------------------------------------------
# Landmark validation — the prototype indexed straight into whatever arrived
# --------------------------------------------------------------------------

def test_valid_landmarks_pass():
    validate_landmarks(make_landmarks())


def test_missing_landmarks_rejected():
    with pytest.raises(InvalidLandmarksError):
        validate_landmarks(None)


def test_wrong_landmark_count_rejected():
    """A short array previously raised IndexError from deep inside extraction."""
    with pytest.raises(InvalidLandmarksError) as exc:
        validate_landmarks([[0.5, 0.5, 0.0]] * 10)
    assert "478" in str(exc.value)


def test_coordinates_far_outside_the_frame_rejected():
    """Out-of-range values silently skewed every feature."""
    bad = make_landmarks()
    bad[1] = [9.9, 9.9, 0.0]
    with pytest.raises(InvalidLandmarksError):
        validate_landmarks(bad)


def test_non_numeric_coordinates_rejected():
    bad = make_landmarks()
    bad[1] = ["x", "y", 0.0]
    with pytest.raises(InvalidLandmarksError):
        validate_landmarks(bad)


def test_slightly_outside_the_frame_is_allowed():
    """A face partly out of frame is legitimate, not corrupt."""
    edge = make_landmarks()
    edge[1] = [1.1, -0.1, 0.0]
    validate_landmarks(edge)


# --------------------------------------------------------------------------
# Feature extraction
# --------------------------------------------------------------------------

def test_extraction_returns_nine_finite_numbers():
    features = extract_features(make_landmarks())
    assert len(features) == len(FEATURE_NAMES) == 9
    assert all(isinstance(v, float) and math.isfinite(v) for v in features)


def test_none_landmarks_give_none_not_an_error():
    assert extract_features(None) is None


def test_extraction_is_deterministic():
    assert extract_features(make_landmarks(7)) == extract_features(make_landmarks(7))


def test_blink_rate_and_eye_openness_are_the_same_value():
    """
    Documented limitation, pinned so nobody assumes they are independent.
    A blink lasts 100-400 ms and frames are sampled once per second, so a real
    blink rate cannot be measured from this input. See docs/model/model-card.md.
    """
    features = extract_features(make_landmarks())
    blink = features[FEATURE_NAMES.index("blink_rate")]
    openness = features[FEATURE_NAMES.index("eye_openness")]
    assert blink == openness


def test_feature_order_is_the_documented_one():
    """Load-bearing: reordering produces confident nonsense, not an error."""
    assert FEATURE_NAMES == [
        "gaze_x", "gaze_y", "blink_rate", "pitch", "yaw",
        "roll", "eye_openness", "brow_raise", "inter_brow",
    ]


def test_extraction_can_skip_validation_for_speed():
    assert extract_features(make_landmarks(), validate=False) is not None


# --------------------------------------------------------------------------
# Artifacts and model — smoke test
# --------------------------------------------------------------------------

def test_artifact_hashes_match_the_manifest():
    """A silently changed model produces plausible but wrong output."""
    results = ml_model.verify_artifacts()
    assert results, "manifest lists no artifacts"
    for filename, ok in results.items():
        assert ok, f"{filename} does not match its recorded hash"


def test_manifest_records_shape_and_class_mapping():
    manifest = ml_model.load_manifest()
    assert manifest["input_shape"] == [10, 9]
    assert manifest["class_mapping"] == {"0": "focused", "1": "drifting", "2": "struggling"}
    assert manifest["feature_order"] == FEATURE_NAMES


def test_model_loads_and_predicts():
    features = extract_features(make_landmarks())
    result = ml_model.predict([features] * 10)
    assert result["state"] in ("focused", "drifting", "struggling")
    assert 0.0 <= result["confidence"] <= 1.0


def test_class_labels_are_lowercase_for_the_contract():
    assert set(ml_model.STATE_LABELS.values()) == {"focused", "drifting", "struggling"}


def test_wrong_window_length_rejected():
    features = extract_features(make_landmarks())
    with pytest.raises(ValueError):
        ml_model.predict([features] * 5)


def test_wrong_feature_count_rejected():
    with pytest.raises(ValueError):
        ml_model.predict([[0.0] * 7] * 10)

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
# Real head pose (opt-in, Phase 1 of the 2026-10-03 accuracy work) - must
# NOT change extract_features' default behavior, since the currently
# shipped model/scaler were fitted on the simplified formula (see
# docs/model/model-card.md and features.py's own estimate_head_pose
# docstring). use_real_head_pose=False (the default) must remain
# byte-for-byte what it always was.
# --------------------------------------------------------------------------

def test_use_real_head_pose_defaults_to_false_and_changes_nothing():
    landmarks = make_landmarks(3)
    assert extract_features(landmarks) == extract_features(landmarks, use_real_head_pose=False)


def test_use_real_head_pose_true_produces_different_pitch_yaw_roll():
    landmarks = make_landmarks(3)
    simplified = extract_features(landmarks)
    real = extract_features(landmarks, use_real_head_pose=True)
    pitch_i, yaw_i, roll_i = (FEATURE_NAMES.index(n) for n in ("pitch", "yaw", "roll"))
    assert (simplified[pitch_i], simplified[yaw_i], simplified[roll_i]) != (
        real[pitch_i], real[yaw_i], real[roll_i],
    )
    # Every other feature is untouched by the pose source.
    for i in range(len(FEATURE_NAMES)):
        if i in (pitch_i, yaw_i, roll_i):
            continue
        assert simplified[i] == real[i]


def test_use_real_head_pose_returns_none_for_the_whole_frame_when_geometry_is_degenerate(monkeypatch):
    """solve_head_pose can return None (degenerate geometry) where the old
    simplified formula never failed. Treated the same as missing landmarks -
    the frame is unusable, not silently given a fake zero pose."""
    from ml.inference import head_pose

    monkeypatch.setattr(head_pose, "solve_head_pose", lambda landmarks: None)
    assert extract_features(make_landmarks(), use_real_head_pose=True) is None


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


def test_the_applied_threshold_is_the_one_the_manifest_documents():
    # The code applies 0.36 while the manifest also carries the exported
    # artifact's own 0.34. Both are legitimate and both are explained in the
    # manifest - but the explanation is only trustworthy while it names the
    # number that is actually applied, so changing one without the other fails.
    variant = ml_model.load_manifest()["calibrated_variant"]
    assert variant["production_threshold"] == ml_model.CALIBRATED_STRUGGLING_THRESHOLD
    assert variant["recommended_threshold"] != variant["production_threshold"]
    assert "production_threshold_note" in variant


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


def _stub_predict(monkeypatch, probs):
    import numpy as np

    class _Model:
        def predict(self, x, verbose=0):
            return np.array([probs])

    class _Scaler:
        def transform(self, a):
            return a

    monkeypatch.setattr(ml_model, "load_model", lambda calibrated=False: (_Model(), _Scaler()))


def test_threshold_rule_flags_struggling_at_or_above_the_threshold(monkeypatch):
    _stub_predict(monkeypatch, [0.2, 0.2, 0.6])
    result = ml_model.predict([[0.0] * 9] * 10, struggling_threshold=0.40, drifting_weight=0.5)
    assert result["state"] == "struggling"


def test_threshold_rule_down_weights_drifting_below_the_threshold(monkeypatch):
    _stub_predict(monkeypatch, [0.5, 0.45, 0.05])
    result = ml_model.predict([[0.0] * 9] * 10, struggling_threshold=0.40, drifting_weight=0.5)
    assert result["state"] == "focused"


def test_uncalibrated_path_is_plain_argmax_and_ignores_the_weight(monkeypatch):
    _stub_predict(monkeypatch, [0.2, 0.5, 0.3])
    result = ml_model.predict([[0.0] * 9] * 10, drifting_weight=0.1)
    assert result["state"] == "drifting"

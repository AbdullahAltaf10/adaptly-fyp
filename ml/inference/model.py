"""
Loading and running the trained engagement model.

Kept free of any web framework so it can be exercised from a notebook, a test,
or an evaluation script without starting a server.

Input:  (1, 10, 9)  - 10 one-second windows, 9 features each
Output: one of focused / drifting / struggling, with a confidence

The artifacts live in ml/artifacts/ and their hashes are recorded in
MANIFEST.json. A model or scaler that changes silently produces plausible but
wrong predictions, which is much harder to notice than a crash - so verify the
hashes when anything looks off.
"""

import hashlib
import json
import os

import numpy as np

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")

MODEL_FILE = "best_model_9f.keras"
SCALER_FILE = "scaler_9f.pkl"
MANIFEST_FILE = "MANIFEST.json"

# Index -> label. Lowercase to match shared/contracts/engagement-event.schema.json.
STATE_LABELS = {0: "focused", 1: "drifting", 2: "struggling"}

WINDOW_SIZE = 10
FEATURE_COUNT = 9

_model = None
_scaler = None


def artifact_path(filename: str) -> str:
    return os.path.join(ARTIFACT_DIR, filename)


def file_sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_manifest() -> dict:
    with open(artifact_path(MANIFEST_FILE), "r") as handle:
        return json.load(handle)


def verify_artifacts() -> dict:
    """
    Compare the artifacts on disk against the recorded hashes.

    Returns {filename: bool}. Not called automatically on every prediction -
    hashing a 417 KB model on each request would be wasteful - but worth running
    whenever predictions look wrong, and in CI.
    """
    manifest = load_manifest()
    results = {}
    for filename, recorded in manifest["artifacts"].items():
        path = artifact_path(filename)
        results[filename] = os.path.exists(path) and file_sha256(path) == recorded["sha256"]
    return results


def load_model():
    """Load the model and scaler once, on first use."""
    global _model, _scaler
    if _model is not None:
        return _model, _scaler

    # TensorFlow is imported here rather than at module level: importing it
    # takes 13+ seconds, and doing that at import time delayed server startup
    # and blocked the first prediction.
    import pickle

    import tensorflow as tf

    model_path = artifact_path(MODEL_FILE)
    scaler_path = artifact_path(SCALER_FILE)
    for path in (model_path, scaler_path):
        if not os.path.exists(path):
            raise RuntimeError(f"Missing model artifact: {path}")

    _model = tf.keras.models.load_model(model_path)
    with open(scaler_path, "rb") as handle:
        _scaler = pickle.load(handle)
    return _model, _scaler


def predict(feature_sequence) -> dict:
    """
    feature_sequence: 10 windows of 9 features, already calibration-corrected.

    Returns {"state": str, "confidence": float}.
    """
    if len(feature_sequence) != WINDOW_SIZE:
        raise ValueError(f"expected {WINDOW_SIZE} frames, got {len(feature_sequence)}")
    for frame in feature_sequence:
        if len(frame) != FEATURE_COUNT:
            raise ValueError(f"expected {FEATURE_COUNT} features per frame, got {len(frame)}")

    model, scaler = load_model()

    array = np.array(feature_sequence, dtype=float)
    scaled = scaler.transform(array)
    probabilities = model.predict(scaled.reshape(1, WINDOW_SIZE, FEATURE_COUNT), verbose=0)[0]

    predicted = int(np.argmax(probabilities))
    return {
        "state": STATE_LABELS[predicted],
        "confidence": round(float(probabilities[predicted]), 4),
    }

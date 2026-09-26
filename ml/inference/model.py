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

# Two artifact pairs, and which one is correct depends on the caller.
#
# The calibrated model was trained on per-subject-centred features. Feeding it
# raw ones is not a smaller version of the same thing, it is a different input
# distribution - measured on the DAiSEE test split:
#
#   configuration                          recall   lift  subjects  flag rate
#   shipped model, raw          (today)     0.099  0.80x         6      0.123
#   calibrated, centred, tau=0.36           0.212  1.13x        13      0.187
#   calibrated, RAW, tau=0.36  (mismatch)   0.355  0.99x        12      0.357
#
# The mismatch row looks like the best recall on the page and is the worst
# option on it: a lift of 0.99x means those flags carry no more information
# than flagging at random, and it interrupts the learner on a third of all
# windows to achieve that. Recall alone would have chosen it.
#
# So the calibrated pair is used only when the features really were centred,
# which is why `predict` takes `calibrated` rather than reading a global.
MODEL_FILE = "best_model_9f.keras"
SCALER_FILE = "scaler_9f.pkl"
CALIBRATED_MODEL_FILE = "best_model_9f_calibrated.keras"
CALIBRATED_SCALER_FILE = "scaler_9f_calibrated.pkl"
MANIFEST_FILE = "MANIFEST.json"

# Chosen by ml/evaluation/calibrated_threshold.py under an explicit rule:
# precision lift >= 1.15 and flag rate <= 0.25, then maximise recall. Lower
# thresholds reach more learners - tau=0.30 reaches 15 of 19 - but at a 0.358
# flag rate, which is a learner interrupted on a third of their windows.
CALIBRATED_STRUGGLING_THRESHOLD = 0.36

# Index -> label. Lowercase to match shared/contracts/engagement-event.schema.json.
STATE_LABELS = {0: "focused", 1: "drifting", 2: "struggling"}
STRUGGLING_INDEX = 2

WINDOW_SIZE = 10
FEATURE_COUNT = 9

# Cached per variant: a session can contain both calibrated and uncalibrated
# learners, so neither may evict the other.
_loaded = {}


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


def load_model(calibrated: bool = False):
    """Load a model/scaler pair once, on first use.

    `calibrated=True` returns the per-subject-centred pair. Callers must only
    ask for it when the features they are about to pass were actually centred
    (see the table above).
    """
    key = "calibrated" if calibrated else "plain"
    if key in _loaded:
        return _loaded[key]

    # TensorFlow is imported here rather than at module level: importing it
    # takes 13+ seconds, and doing that at import time delayed server startup
    # and blocked the first prediction.
    import pickle

    import tensorflow as tf

    model_file = CALIBRATED_MODEL_FILE if calibrated else MODEL_FILE
    scaler_file = CALIBRATED_SCALER_FILE if calibrated else SCALER_FILE
    model_path = artifact_path(model_file)
    scaler_path = artifact_path(scaler_file)
    for path in (model_path, scaler_path):
        if not os.path.exists(path):
            raise RuntimeError(f"Missing model artifact: {path}")

    model = tf.keras.models.load_model(model_path)
    with open(scaler_path, "rb") as handle:
        scaler = pickle.load(handle)
    _loaded[key] = (model, scaler)
    return _loaded[key]


def predict(feature_sequence, struggling_threshold: float = None,
            calibrated: bool = False) -> dict:
    """
    feature_sequence: 10 windows of 9 features, already calibration-corrected.

    Returns {"state": str, "confidence": float}.

    `struggling_threshold` is opt-in and defaults to None, which keeps the
    plain argmax this has always used - existing callers are unaffected.
    Passing a value applies a one-sided override: report "struggling" whenever
    its probability clears the threshold, even when another class is more
    likely, and otherwise take the argmax of the remaining classes.

    Why only Struggling gets a lowered bar
    --------------------------------------
    argmax is the right rule only when a false positive costs the same as a
    false negative. Scope section 6.4 delivers interventions "without any
    sound, flash, or alert", inline and dismissible, so a false alarm is cheap
    while a missed struggling learner gets no help at all. The other two
    classes carry no such asymmetry.

    Measured on a per-subject-centred model (ml/evaluation/calibrated_threshold.py):
    at 0.40, against argmax on the current model, Struggling recall rises from
    0.142 to 0.197, the number of distinct learners reached doubles, and
    precision moves from 0.80x the class base rate - worse than flagging at
    random - to 1.23x.

    Still not applied to the uncalibrated model, and that is not caution - it
    buys nothing there (ml/evaluation/threshold_sweep.py). That model's
    Struggling precision is already below the class base rate, so lowering the
    bar only adds noise to flags that were no better than random to begin with.

    `calibrated` selects the per-subject-centred artifacts, and the caller is
    responsible for only setting it when the features really were centred.
    When it is set, the engagement route also supplies
    CALIBRATED_STRUGGLING_THRESHOLD; the two belong together, because the
    calibrated model at plain argmax is *worse* than what ships today
    (recall 0.064 against 0.099). The gain is the pair, not either half.
    """
    if len(feature_sequence) != WINDOW_SIZE:
        raise ValueError(f"expected {WINDOW_SIZE} frames, got {len(feature_sequence)}")
    for frame in feature_sequence:
        if len(frame) != FEATURE_COUNT:
            raise ValueError(f"expected {FEATURE_COUNT} features per frame, got {len(frame)}")

    model, scaler = load_model(calibrated=calibrated)

    array = np.array(feature_sequence, dtype=float)
    scaled = scaler.transform(array)
    probabilities = model.predict(scaled.reshape(1, WINDOW_SIZE, FEATURE_COUNT), verbose=0)[0]

    if (struggling_threshold is not None
            and probabilities[STRUGGLING_INDEX] >= struggling_threshold):
        predicted = STRUGGLING_INDEX
    else:
        predicted = int(np.argmax(probabilities))

    return {
        "state": STATE_LABELS[predicted],
        "confidence": round(float(probabilities[predicted]), 4),
        # Every class's probability, not only the winner's.
        #
        # A caller that reports a DIFFERENT state than this function returned -
        # the smoothing layer holding a previous state through a transition,
        # for instance - needs the probability of the state it actually
        # reports. Without this it can only report the winner's confidence
        # beside somebody else's label.
        "probabilities": {
            STATE_LABELS[index]: round(float(value), 4)
            for index, value in enumerate(probabilities)
        },
    }

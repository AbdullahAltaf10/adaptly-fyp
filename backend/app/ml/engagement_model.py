import os
import pickle
import numpy as np

# TensorFlow is deliberately NOT imported at module level. Importing it takes
# ~15-20 seconds, and because this module is reachable from main.py, that delay
# ran before uvicorn began accepting connections — so a browser opened during
# startup got connection-refused and the app stalled on "Loading profile...".
# The import now happens on the first prediction instead.

ML_DIR = os.path.dirname(__file__)

_model = None
_scaler = None

STATE_LABELS = {0: "Focused", 1: "Drifting", 2: "Struggling"}


def load_engagement_model():
    global _model, _scaler
    if _model is None:
        import tensorflow as tf  # deferred — see note at top of file

        _model = tf.keras.models.load_model(os.path.join(ML_DIR, "best_model_9f.keras"))
    if _scaler is None:
        with open(os.path.join(ML_DIR, "scaler_9f.pkl"), "rb") as f:
            _scaler = pickle.load(f)
    return _model, _scaler


def predict_engagement(feature_sequence: list) -> dict:
    """
    feature_sequence: list of 10 frames, each a list of 9 floats
    (already calibration-corrected, if calibration is active for this user)
    """
    model, scaler = load_engagement_model()

    X = np.array(feature_sequence).reshape(1, 10, 9)
    X_flat = X.reshape(-1, 9)
    X_scaled = scaler.transform(X_flat).reshape(1, 10, 9)

    prediction = model.predict(X_scaled, verbose=0)
    predicted_class = int(prediction.argmax(axis=1)[0])
    confidence = float(prediction.max())

    return {
        "state": STATE_LABELS[predicted_class],
        "confidence": round(confidence, 4),
    }
import os
import json
import numpy as np

ML_DIR = os.path.dirname(__file__)

FEATURE_NAMES = [
    "gaze_x", "gaze_y", "blink_rate", "pitch", "yaw",
    "roll", "eye_openness", "brow_raise", "inter_brow",
]

_reference_means = None


def load_reference_means():
    global _reference_means
    if _reference_means is None:
        with open(os.path.join(ML_DIR, "focused_reference_means.json"), "r") as f:
            data = json.load(f)
        _reference_means = np.array([data[name] for name in FEATURE_NAMES])
    return _reference_means


def compute_user_baseline(calibration_frames: list) -> list:
    valid_frames = [f for f in calibration_frames if f is not None]
    if not valid_frames:
        return None
    arr = np.array(valid_frames)
    return arr.mean(axis=0).tolist()


def compute_offset(user_baseline: list) -> list:
    reference = load_reference_means()
    user_arr = np.array(user_baseline)
    return (user_arr - reference).tolist()


def apply_calibration(feature_sequence: list, offset: list) -> list:
    offset_arr = np.array(offset)
    corrected = []
    for frame in feature_sequence:
        if frame is None:
            corrected.append(None)
        else:
            corrected_frame = (np.array(frame) - offset_arr).tolist()
            corrected.append(corrected_frame)
    return corrected
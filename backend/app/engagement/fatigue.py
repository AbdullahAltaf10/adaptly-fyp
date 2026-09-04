"""
Rule-based Fatigued detector.

DAiSEE has no fatigue dimension, so Fatigued cannot be a model class (see
PROJECT_CONTEXT section 4). It is derived here instead: sustained low eye
openness relative to the user's own calibrated baseline.

How the threshold is grounded
-----------------------------
`eye_openness` is the mean eye-aspect-ratio of both eyes. DAiSEE's Focused
population sits at mean 0.369, std 0.068. Calibration rebases each user onto
that scale (offset = user_baseline - reference), so after calibration a value
near 0.369 means "as open-eyed as an alert DAiSEE subject" and drifting below
it means this particular person's eyes are drooping relative to their own
alert baseline.

This only holds for calibrated users. Uncalibrated live EAR averages ~0.311
(section 4), which sits barely above the threshold — so an uncalibrated user
would trip the rule almost immediately. `update()` therefore refuses to run
without calibration rather than reporting a meaningless answer.

Blink robustness
----------------
Each window's value is the MEDIAN of its 10 frames, not the mean. A blink
drives EAR toward zero for a frame or two, and the route also substitutes
zero-vectors for any leading frames captured before the first face detection.
The frontend guarantees at least 7 of 10 frames contain a real face, so a
median over 10 values cannot be dragged below the threshold by either effect.
"""

import json
import os
import time

from app.engagement.calibration import load_reference_means

ML_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "ml", "artifacts",
)  # repo_root/ml/artifacts - the single copy of the reference means

GAZE_Y_INDEX = 1        # [gaze_x, gaze_y, blink_rate, pitch, yaw, roll, eye_openness, ...]
PITCH_INDEX = 3
EYE_OPENNESS_INDEX = 6

# Looking down at a keyboard drops the eyelids over the eyes, which lowers EAR
# exactly like drooping from tiredness does. Genuine fatigue means drooping eyes
# with the user still LOOKING AT THE SCREEN, so "looking down" windows are
# excluded from the history rather than counted as droop.
#
# MEASURED sign convention: head down => pitch delta POSITIVE.
# Tilting the head down foreshortens the lower face, so the projected
# nose-to-chin distance shrinks and pitch rises toward zero. Measured live at
# +8.84 with the head deliberately down.
#
# This was originally implemented with the opposite sign, carried over from the
# section 4 laptop-camera comparison (live -19.75 vs DAiSEE -13.38). That figure
# describes a CAMERA MOUNTING difference between two datasets, not what happens
# when one person tilts their head — so it was the wrong convention to reuse,
# and the gate never fired.
#
# Threshold sits well below the observed +8.84 so a moderate downward glance
# still trips it.
HEAD_DOWN_DELTA = 3.0

# Preferred gate: solvePnP pitch relative to the user's calibrated pose baseline.
# Distance-invariant and much less contaminated by jaw movement than the
# simplified estimate. Used when a pose baseline exists; otherwise the simplified
# gate above applies, so users calibrated before solvePnP was added keep working
# until they recalibrate.
#
# MEASURED FROM A REAL SESSION, and this sign was wrong twice before.
#
# Live reading while typing and looking at a keyboard: solvePnP pitch delta
# = +7 degrees. So head down => POSITIVE, the same direction as the simplified
# estimate, not the opposite.
#
# An earlier version used -8.0 because a synthetic test appeared to show head
# down going negative. That test built its own rotation and then measured it,
# so it only confirmed the assumption it was written from — it never described
# what a real camera and a real face produce. The gate could therefore never
# fire, and fatigue kept accumulating while the user was actively typing.
# Trust the live number over the synthetic one.
#
# Threshold set below the measured +7 so an ordinary glance down still trips it,
# while normal sitting (near 0, since this is relative to the user's own
# calibrated baseline) does not.
HEAD_DOWN_DEGREES = 4.0

# A gaze-direction gate was tried here too, on the theory that looking at a
# keyboard is done with the eyes more than the head. Measured gaze delta with
# the head down was -0.0036 — the eyes look UP within the socket to keep the
# screen in view, so gaze_y does not cleanly indicate "looking down". Removed
# rather than kept with a guessed sign; see the memory note about keeping
# content out of the lower screen area, which addresses this by layout instead.

# DAiSEE Focused std for eye_openness. The reference-means JSON stores means
# only, so this is recorded here from the same measurement (PROJECT_CONTEXT
# section 4). If a stds file is ever added, load it from there instead.
REFERENCE_STD = 0.068
K_STD = 1.0

HISTORY_WINDOWS = 45   # ~45 seconds at one window per second
MIN_LOW_RATIO = 0.8    # fraction of the history that must be below threshold

SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {"values": [...], "last_seen": float}
_sessions = {}

_threshold = None


def get_threshold() -> float:
    """Eye-openness level below which a window counts as 'drooping'."""
    global _threshold
    if _threshold is None:
        with open(os.path.join(ML_DIR, "focused_reference_means.json"), "r") as f:
            reference_mean = json.load(f)["eye_openness"]
        _threshold = reference_mean - K_STD * REFERENCE_STD
    return _threshold


def _median(values: list) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _evict_stale(now: float) -> None:
    stale = [key for key, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def get_reference_pitch() -> float:
    return float(load_reference_means()[PITCH_INDEX])


def get_reference_gaze_y() -> float:
    return float(load_reference_means()[GAZE_Y_INDEX])


def update(uid: str, session_id: str, feature_sequence: list, calibrated: bool,
           pose_pitch_delta=None) -> dict:
    """
    feature_sequence: the 10 calibration-corrected frames for this window.

    Returns the fatigue verdict for the session so far. `fatigued` stays False
    until a full HISTORY_WINDOWS of evidence exists — fatigue is defined as a
    sustained condition, so it deliberately cannot fire in the first ~45s.

    Windows where the head is tilted down are skipped entirely rather than
    counted, so looking at a keyboard does not accumulate as fatigue.
    """
    if not calibrated:
        return {
            "fatigued": False,
            "fatigue_ratio": None,
            "fatigue_available": False,
            "fatigue_head_down": False,
            "fatigue_pitch_delta": None,
            "fatigue_gaze_delta": None,
            "fatigue_pose_pitch": None,
        }

    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.setdefault(key, {"values": [], "last_seen": now})
    session["last_seen"] = now

    pitch_delta = _median([frame[PITCH_INDEX] for frame in feature_sequence]) - get_reference_pitch()
    gaze_delta = _median([frame[GAZE_Y_INDEX] for frame in feature_sequence]) - get_reference_gaze_y()

    if pose_pitch_delta is not None:
        head_down = pose_pitch_delta >= HEAD_DOWN_DEGREES
    else:
        head_down = pitch_delta >= HEAD_DOWN_DELTA

    if not head_down:
        window_value = _median([frame[EYE_OPENNESS_INDEX] for frame in feature_sequence])
        session["values"].append(window_value)
        if len(session["values"]) > HISTORY_WINDOWS:
            session["values"].pop(0)

    diagnostics = {
        "fatigue_head_down": head_down,
        "fatigue_pitch_delta": round(pitch_delta, 2),
        "fatigue_gaze_delta": round(gaze_delta, 4),
        "fatigue_pose_pitch": None if pose_pitch_delta is None else round(pose_pitch_delta, 1),
    }

    values = session["values"]
    if not values:
        # every window so far was skipped — no evidence either way yet
        return {
            "fatigued": False,
            "fatigue_ratio": 0.0,
            "fatigue_available": True,
            **diagnostics,
        }

    threshold = get_threshold()
    low = sum(1 for v in values if v < threshold)
    ratio = low / len(values)

    return {
        "fatigued": len(values) >= HISTORY_WINDOWS and ratio >= MIN_LOW_RATIO,
        "fatigue_ratio": round(ratio, 3),
        "fatigue_available": True,
        **diagnostics,
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's fatigue history (session end, or after recalibration)."""
    _sessions.pop((uid, session_id), None)

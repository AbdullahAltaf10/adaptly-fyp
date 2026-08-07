"""
Rule-based Deep Thinking detector.

Purpose: suppress false disengagement alarms during genuine reflection. A
learner who is thinking hard about a difficult passage looks, to the model,
much like a learner who has checked out — head down, not much movement. The
scope document's proposed discriminator is that reflection is *still* in a
specific way: sustained head-down posture, low blink variance, and stable gaze
fixation, whereas drifting attention wanders.

THRESHOLDS HERE ARE UNVALIDATED PLACEHOLDERS
--------------------------------------------
Unlike the fatigue rule, which is grounded in a measured DAiSEE distribution
(eye_openness mean 0.369, std 0.068), there is no reference distribution for
"stillness". The three constants below were chosen by reasoning about the
feature scales, NOT from data, and they are expected to need tuning against
live readings before this rule can be trusted. The route surfaces the measured
values on every window so they can be tuned by observation.

Treat a firing of this rule as a hypothesis until the constants are tuned.

Sign convention for pitch (measured, and initially got this wrong)
------------------------------------------------------------------
Head down => pitch delta POSITIVE. Tilting the head down foreshortens the
lower face, so the projected nose-to-chin distance shrinks and pitch rises
toward zero. Measured live at +7.39 with the head deliberately down.

This was first implemented with the opposite sign, reasoning from section 4's
note that live laptop users read -19.75 against a DAiSEE reference of -13.38.
That figure describes a difference in CAMERA MOUNTING between two datasets,
not what happens when one person tilts their head — reusing it as a head-tilt
convention was a mistake, and the condition could never pass.

Requires calibration for the same reason the fatigue rule does: the pitch
comparison is only meaningful once the user's own baseline has been mapped
onto the DAiSEE reference scale.
"""

import json
import os
import statistics
import time

ML_DIR = os.path.dirname(__file__)

GAZE_X_INDEX = 0
GAZE_Y_INDEX = 1
BLINK_RATE_INDEX = 2  # same EAR value as eye_openness — see section 4
PITCH_INDEX = 3

BAD_STATES = ("Drifting", "Struggling")

HISTORY_WINDOWS = 15  # ~15s of sustained stillness before reflection is credited

# --- tuned against live readings (head down, holding still) -------------------
# Measured while deliberately still: gaze var 1.40e-6, EAR var 8.43e-4,
# pitch delta +7.39.
GAZE_VARIANCE_MAX = 5e-6   # measured 1.40e-6 when still — original guess held up
EAR_VARIANCE_MAX = 2e-3    # was 1e-4, which measured ~8x too strict to ever pass
PITCH_DOWN_DELTA = 4.0     # head down => pitch delta POSITIVE (measured +7.39);
                           # the original -3.0 had the sign backwards
# Preferred gate when a solvePnP pose baseline exists. Note the OPPOSITE sign:
# solvePnP pitch goes NEGATIVE looking down (verified against synthetic ground
# truth), whereas the simplified estimate goes positive.
PITCH_DOWN_DEGREES = -8.0
# ------------------------------------------------------------------------------

SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {"gx": [...], "gy": [...], "ear": [...], "pitch": [...], "last_seen": float}
_sessions = {}

_reference_pitch = None


def get_reference_pitch() -> float:
    global _reference_pitch
    if _reference_pitch is None:
        with open(os.path.join(ML_DIR, "focused_reference_means.json"), "r") as f:
            _reference_pitch = json.load(f)["pitch"]
    return _reference_pitch


def _evict_stale(now: float) -> None:
    stale = [key for key, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def _unavailable() -> dict:
    return {
        "deep_thinking": False,
        "dt_available": False,
        "dt_gaze_var": None,
        "dt_ear_var": None,
        "dt_pitch_delta": None,
        "dt_gaze_ok": None,
        "dt_ear_ok": None,
        "dt_pitch_ok": None,
        "dt_state_ok": None,
    }


def update(uid: str, session_id: str, feature_sequence: list,
           display_state: str, calibrated: bool, pose_pitch_delta=None) -> dict:
    """
    feature_sequence: the 10 calibration-corrected frames for this window.
    display_state:    the SMOOTHED state, so the override reflects a confirmed
                      disengagement rather than a single noisy prediction.

    The stillness metrics are reported on every window (so they can be tuned),
    but `deep_thinking` only becomes True when the model is actually reporting
    disengagement — there is nothing to suppress otherwise.
    """
    if not calibrated:
        return _unavailable()

    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.setdefault(
        key, {"gx": [], "gy": [], "ear": [], "pitch": [], "last_seen": now}
    )
    session["last_seen"] = now

    # median across the 10 frames, for the same blink/zero-frame robustness
    # reasons documented in fatigue.py
    session["gx"].append(statistics.median([f[GAZE_X_INDEX] for f in feature_sequence]))
    session["gy"].append(statistics.median([f[GAZE_Y_INDEX] for f in feature_sequence]))
    session["ear"].append(statistics.median([f[BLINK_RATE_INDEX] for f in feature_sequence]))
    session["pitch"].append(statistics.median([f[PITCH_INDEX] for f in feature_sequence]))

    for series in ("gx", "gy", "ear", "pitch"):
        if len(session[series]) > HISTORY_WINDOWS:
            session[series].pop(0)

    if len(session["gx"]) < HISTORY_WINDOWS:
        return _unavailable()

    gaze_var = statistics.pvariance(session["gx"]) + statistics.pvariance(session["gy"])
    ear_var = statistics.pvariance(session["ear"])
    pitch_delta = statistics.fmean(session["pitch"]) - get_reference_pitch()

    # Reported individually so it is obvious WHICH condition is blocking a
    # firing. The thresholds are guesses, and guessing again without knowing
    # which one fails would just be a third guess.
    gaze_ok = gaze_var <= GAZE_VARIANCE_MAX
    ear_ok = ear_var <= EAR_VARIANCE_MAX
    if pose_pitch_delta is not None:
        pitch_ok = pose_pitch_delta <= PITCH_DOWN_DEGREES
    else:
        pitch_ok = pitch_delta >= PITCH_DOWN_DELTA
    state_ok = display_state in BAD_STATES

    return {
        "deep_thinking": gaze_ok and ear_ok and pitch_ok and state_ok,
        "dt_available": True,
        "dt_gaze_var": gaze_var,
        "dt_ear_var": ear_var,
        "dt_pitch_delta": round(pitch_delta, 2),
        "dt_gaze_ok": gaze_ok,
        "dt_ear_ok": ear_ok,
        "dt_pitch_ok": pitch_ok,
        "dt_state_ok": state_ok,
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's stillness history (session end, or after recalibration)."""
    _sessions.pop((uid, session_id), None)

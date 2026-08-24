"""
Regression tests for the "looking down" gate in the engagement detectors.

Why this file exists
--------------------
The head-pose sign was implemented backwards THREE times. Each time the result
was the same: the gate became dead code, and fatigue accumulated while the user
was actively typing and looking at their keyboard.

The last attempt was "verified" by a synthetic test that built its own rotation
and then measured it — so it confirmed the assumption it was written from rather
than describing what a real camera produces.

These tests therefore use the LIVE MEASURED value from a real session:

    typing, looking at a keyboard  ->  solvePnP pitch delta = +7 degrees

Head down is POSITIVE. If someone flips this again, these fail immediately.

Run from backend/:   python -m pytest tests/ -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engagement import deep_thinking, fatigue  # noqa: E402

# Live readings from a real session.
KEYBOARD_PITCH = 7.0    # looking down at a keyboard
LEVEL_PITCH = 0.0       # looking at the screen (equals own calibrated baseline)

LOW_EAR = 0.22          # drooping / half-closed eyes
HIGH_EAR = 0.40         # wide awake


def _frame(ear, pitch=0.0):
    f = [0.0] * 9
    f[fatigue.EYE_OPENNESS_INDEX] = ear
    f[fatigue.PITCH_INDEX] = fatigue.get_reference_pitch() + pitch
    return f


def _window(ear, pitch=0.0):
    return [_frame(ear, pitch) for _ in range(10)]


def _feed(sid, ear, n, pose, uid="u"):
    result = None
    for _ in range(n):
        result = fatigue.update(uid, sid, _window(ear), calibrated=True,
                                pose_pitch_delta=pose)
    return result


# --------------------------------------------------------------------------
# The exact bug that was reported
# --------------------------------------------------------------------------

def test_typing_at_keyboard_does_not_accumulate_fatigue():
    """
    Reported live: 'eyes low 71% of 45s, solvePnP pitch 7' while typing.
    Looking down must skip the window entirely, not count it as droop.
    """
    fatigue.reset("u", "kb")
    result = _feed("kb", LOW_EAR, 60, pose=KEYBOARD_PITCH)
    assert result["fatigue_head_down"] is True, "must recognise looking down"
    assert result["fatigued"] is False, "typing must never read as fatigue"
    assert len(fatigue._sessions[("u", "kb")]["values"]) == 0, "no evidence stored"


def test_head_down_is_positive_not_negative():
    """Guards the sign directly. A negative delta is head UP, not down."""
    fatigue.reset("u", "sign")
    down = fatigue.update("u", "sign", _window(LOW_EAR), calibrated=True,
                          pose_pitch_delta=KEYBOARD_PITCH)
    assert down["fatigue_head_down"] is True

    fatigue.reset("u", "sign2")
    up = fatigue.update("u", "sign2", _window(LOW_EAR), calibrated=True,
                        pose_pitch_delta=-KEYBOARD_PITCH)
    assert up["fatigue_head_down"] is False, "negative pitch is head UP"


def test_threshold_sits_below_the_measured_keyboard_value():
    """If someone raises the threshold above +7, keyboard glances stop being caught."""
    assert 0 < fatigue.HEAD_DOWN_DEGREES < KEYBOARD_PITCH
    assert 0 < deep_thinking.PITCH_DOWN_DEGREES < KEYBOARD_PITCH


# --------------------------------------------------------------------------
# The behaviour that must still work
# --------------------------------------------------------------------------

def test_drooping_eyes_while_facing_the_screen_still_fires():
    fatigue.reset("u", "tired")
    result = _feed("tired", LOW_EAR, fatigue.HISTORY_WINDOWS, pose=LEVEL_PITCH)
    assert result["fatigued"] is True


def test_alert_eyes_never_fire():
    fatigue.reset("u", "awake")
    result = _feed("awake", HIGH_EAR, 60, pose=LEVEL_PITCH)
    assert result["fatigued"] is False


def test_typing_does_not_erase_genuine_fatigue_evidence():
    """Looking down pauses collection; it must not reset what was already seen."""
    fatigue.reset("u", "mixed")
    _feed("mixed", LOW_EAR, 30, pose=LEVEL_PITCH)      # genuinely tired
    _feed("mixed", HIGH_EAR, 30, pose=KEYBOARD_PITCH)  # typing, ignored
    result = _feed("mixed", LOW_EAR, 15, pose=LEVEL_PITCH)
    assert result["fatigued"] is True


def test_first_window_looking_down_does_not_crash():
    fatigue.reset("u", "first")
    result = fatigue.update("u", "first", _window(LOW_EAR), calibrated=True,
                            pose_pitch_delta=KEYBOARD_PITCH)
    assert result["fatigue_ratio"] == 0.0


def test_uncalibrated_user_is_refused():
    fatigue.reset("u", "nocal")
    result = fatigue.update("u", "nocal", _window(LOW_EAR), calibrated=False)
    assert result["fatigue_available"] is False


# --------------------------------------------------------------------------
# Deep thinking uses the same convention
# --------------------------------------------------------------------------

def test_deep_thinking_head_down_uses_the_same_sign():
    deep_thinking.reset("u", "dt")
    result = None
    for _ in range(deep_thinking.HISTORY_WINDOWS):
        result = deep_thinking.update("u", "dt", _window(0.30), "drifting",
                                      calibrated=True,
                                      pose_pitch_delta=KEYBOARD_PITCH)
    assert result["dt_pitch_ok"] is True, "positive delta must count as head down"


def test_deep_thinking_head_up_is_not_head_down():
    deep_thinking.reset("u", "dt2")
    result = None
    for _ in range(deep_thinking.HISTORY_WINDOWS):
        result = deep_thinking.update("u", "dt2", _window(0.30), "drifting",
                                      calibrated=True,
                                      pose_pitch_delta=-KEYBOARD_PITCH)
    assert result["dt_pitch_ok"] is False

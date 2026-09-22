"""
Brow-furrow measurement (provisional — reports only, does not change state).

Why this exists
---------------
Furrowing the forehead is the clearest visible confusion signal, but in
practice it reads as Focused most of the time. That is not a bug: Struggling
recall is only 10-18% (PROJECT_CONTEXT section 5), and the model's two brow
features are exactly what lifted it from ~1% to that range (section 4). The
signal is present but weak.

Why this does NOT override the state yet
----------------------------------------
Fatigued, Recovered and Deep Thinking are states the model cannot produce at
all, so a rule is the only way to get them. Struggling IS a model class.
A rule that forces Struggling would partly bypass the model on its most
product-critical output, so it should not be switched on from a guessed
threshold. This module therefore MEASURES and reports, so the threshold can be
set from real observations, and the override can be enabled deliberately
afterwards.

What it measures
----------------
Furrowing pulls the inner eyebrows together and lowers them, so both
`inter_brow` (inner-brow separation) and `brow_raise` (brow-to-eye distance)
shrink. Both are reported as a ratio against the DAiSEE Focused reference.
Calibration has already rebased the user onto that scale, so 1.0 means "at
your own resting baseline" and lower means "more furrowed".

FURROW_RATIO_MAX below is an UNVALIDATED starting guess, like the Deep
Thinking constants. Tune it by watching the live readout while furrowing.
"""

import math
import time

from ml.inference import head_pose
from ml.inference.features import (
    LEFT_EYE_UPPER,
    LEFT_EYEBROW,
    LEFT_EYEBROW_INNER,
    RIGHT_EYE_UPPER,
    RIGHT_EYEBROW,
    RIGHT_EYEBROW_INNER,
    eyebrow_eye_distance,
)


def normalised_brow(landmarks):
    """
    Brow measurements divided by inter-ocular distance, making them independent
    of how close the user sits.

    This is the fix for furrow firing when the user is perfectly relaxed: the
    raw distances scale with apparent face size, so sitting ~8% further from the
    camera shrank inter_brow ~8% and crossed the threshold with no furrow at all.
    Dividing by another distance on the same face cancels that entirely.

    returns (inter_brow_norm, brow_raise_norm) or None.
    """
    if landmarks is None:
        return None
    iod = head_pose.inter_ocular_distance(landmarks)
    if iod is None:
        return None
    try:
        inter = math.dist(landmarks[LEFT_EYEBROW_INNER][:2], landmarks[RIGHT_EYEBROW_INNER][:2])
        left = eyebrow_eye_distance(landmarks, LEFT_EYEBROW, LEFT_EYE_UPPER)
        right = eyebrow_eye_distance(landmarks, RIGHT_EYEBROW, RIGHT_EYE_UPPER)
        return (inter / iod, ((left + right) / 2.0) / iod)
    except (IndexError, TypeError, ValueError):
        return None


def mean_normalised_brow(frames_landmarks):
    """Mean normalised brow measurements across frames, for the calibration baseline."""
    values = [normalised_brow(lm) for lm in frames_landmarks]
    values = [v for v in values if v is not None]
    if not values:
        return None
    return [
        sum(v[0] for v in values) / len(values),
        sum(v[1] for v in values) / len(values),
    ]

HISTORY_WINDOWS = 3    # short — furrowing is a fast expression, not a posture

# Measurements are now normalised by inter-ocular distance (see normalised_brow),
# which removes the distance sensitivity that made this fire constantly: raw brow
# distances scale with apparent face size, so sitting ~8% further away shrank
# inter_brow ~8% and crossed the threshold with no furrow at all.
#
# Normalisation does NOT fix head rotation, which foreshortens the brow region
# non-uniformly. Measured with the head merely tilted down and no furrow:
#     inter-brow 1.2616, brow-raise 0.3806
# so off-pose windows are still rejected outright rather than reported.
MAX_POSE_DELTA_DEG = 10.0

# --- placeholder constant, tune against the live readout ----------------------
FURROW_RATIO_MAX = 0.92   # inter_brow this far below baseline counts as furrowed
# ------------------------------------------------------------------------------

SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {"inter": [...], "raise": [...], "last_seen": float}
_sessions = {}


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


def _unavailable() -> dict:
    return {
        "furrowed": False,
        "furrow_available": False,
        "furrow_ratio": None,
        "furrow_brow_ratio": None,
        "furrow_off_pose": False,
    }


def update(uid: str, session_id: str, frames_landmarks: list, brow_baseline,
           pose_pitch_delta, calibrated: bool) -> dict:
    """
    frames_landmarks: raw landmarks for this window, needed for scale normalisation.
    brow_baseline:    the user's own normalised brow measurements captured at
                      calibration; without it there is nothing to compare against.
    pose_pitch_delta: solvePnP pitch relative to the user's pose baseline, in
                      degrees, or None when unavailable.

    Reports how furrowed the brow is relative to the user's own baseline.
    `furrowed` is advisory only — the route does not use it to change state.
    """
    if not calibrated or not brow_baseline:
        return _unavailable()

    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.setdefault(key, {"inter": [], "raise": [], "last_seen": now})
    session["last_seen"] = now

    # Head off-pose => brow geometry is dominated by perspective, so any furrow
    # number would be noise. Discard the history so a stale pre-tilt reading is
    # not averaged into the next valid one.
    if pose_pitch_delta is not None and abs(pose_pitch_delta) > MAX_POSE_DELTA_DEG:
        session["inter"].clear()
        session["raise"].clear()
        return {**_unavailable(), "furrow_off_pose": True}

    measurements = [normalised_brow(lm) for lm in frames_landmarks]
    measurements = [m for m in measurements if m is not None]
    if not measurements:
        return _unavailable()

    session["inter"].append(_median([m[0] for m in measurements]))
    session["raise"].append(_median([m[1] for m in measurements]))
    for series in ("inter", "raise"):
        if len(session[series]) > HISTORY_WINDOWS:
            session[series].pop(0)

    base_inter, base_raise = brow_baseline
    if base_inter <= 0 or base_raise <= 0:
        return _unavailable()

    inter_ratio = (sum(session["inter"]) / len(session["inter"])) / base_inter
    raise_ratio = (sum(session["raise"]) / len(session["raise"])) / base_raise

    # A real furrow pulls the brows together AND lowers them, so both ratios
    # must sit below baseline. Requiring only inter_brow flagged a furrow while
    # brow_raise read 1.11 — i.e. brows further from the eyes, the opposite of
    # furrowing. Caveat: squinting hard pushes brow_raise back up, so if this
    # stops catching your furrow, relax the brow_raise side rather than the
    # inter_brow side.
    furrowed = (
        len(session["inter"]) >= HISTORY_WINDOWS
        and inter_ratio <= FURROW_RATIO_MAX
        and raise_ratio <= 1.0
    )

    return {
        # advisory only until the threshold is tuned — see module docstring
        "furrowed": furrowed,
        "furrow_available": True,
        "furrow_ratio": round(inter_ratio, 4),
        "furrow_brow_ratio": round(raise_ratio, 4),
        "furrow_off_pose": False,
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's furrow history (session end, or after recalibration)."""
    _sessions.pop((uid, session_id), None)

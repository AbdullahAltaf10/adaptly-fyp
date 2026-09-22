"""
Rule-based Recovered detector.

"Recovered" is inherently relative — it means "came back from a bad state" —
so it cannot be a model class trained on single static clips (PROJECT_CONTEXT
section 4). It is derived here by comparing the current state against the
session's recent state history.

Definition used
---------------
A recovery fires when the learner has been in a bad state (Drifting or
Struggling) for at least MIN_BAD_RUN consecutive windows and then reaches
Focused. It then displays for DISPLAY_WINDOWS windows and expires.

Three deliberate choices:

1. This consumes the SMOOTHED state, not the raw prediction. Raw predictions
   flip between classes on single noisy frames, which would manufacture
   recoveries out of nothing. Feeding it the already-confirmed state means a
   recovery reflects a real, sustained change.

2. The bad run counts consecutive windows in ANY bad state, not in one
   specific state. Someone who drifts for 6 windows, struggles for 6, then
   refocuses has genuinely been struggling for 12 windows — splitting that
   into two short runs would miss an obvious recovery.

3. Slipping back cancels the display immediately. Someone who returns to
   Drifting two seconds after refocusing has not recovered, and continuing to
   show it would be actively misleading.
"""

import time

BAD_STATES = ("drifting", "struggling")
GOOD_STATE = "focused"

MIN_BAD_RUN = 10      # windows in a bad state before a return counts as recovery
DISPLAY_WINDOWS = 10  # how long "Recovered" stays up once triggered

SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {"bad_run": int, "remaining": int, "last_seen": float}
_sessions = {}


def _evict_stale(now: float) -> None:
    stale = [key for key, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def update(uid: str, session_id: str, display_state: str) -> dict:
    """
    display_state: the SMOOTHED state for this window, not the raw prediction.
    """
    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.setdefault(key, {"bad_run": 0, "remaining": 0, "last_seen": now})
    session["last_seen"] = now

    if display_state in BAD_STATES:
        session["bad_run"] += 1
        session["remaining"] = 0  # slipped back — cancel any active recovery
    else:
        if display_state == GOOD_STATE and session["bad_run"] >= MIN_BAD_RUN:
            session["remaining"] = DISPLAY_WINDOWS
        elif session["remaining"] > 0:
            session["remaining"] -= 1
        session["bad_run"] = 0

    return {
        "recovered": session["remaining"] > 0,
        "recovery_remaining": session["remaining"],
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's recovery history (session end, or after recalibration)."""
    _sessions.pop((uid, session_id), None)

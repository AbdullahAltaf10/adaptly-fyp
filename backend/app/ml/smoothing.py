"""
Temporal smoothing for engagement predictions.

The model predicts over a 10-frame window, and StudySession sends a new window
every second. Consecutive windows overlap by 9 of their 10 frames, so a single
noisy frame can flip the predicted state and flip it back a second later.

This layer holds the *displayed* state steady until a candidate state has been
confirmed by N consecutive raw predictions. It is the application-layer
substitute for the 30-second window in the scope document (see PROJECT_CONTEXT
section 4 — the model is trained on 10-second DAiSEE clips and cannot be given a
true 30-second window without stitching non-continuous clips together).

Honest caveat: because windows overlap by 9 frames, N consecutive agreeing
windows represent only N *new* frames of evidence, not N x 10 seconds. This is
genuine noise rejection, but it is weaker than "30 seconds of agreement" implies.

Thresholds are asymmetric by target state:
  - returning to Focused is cheap, so a recovering learner sees it quickly
  - entering Drifting/Struggling is expensive, so a stray prediction cannot
    raise a false alarm. Struggling recall is only 10-18% (PROJECT_CONTEXT
    section 5), which makes a single Struggling window a weak signal.
"""

import time

CONFIRMATION_WINDOWS = {
    "Focused": 2,      # fast recovery
    "Drifting": 3,
    "Struggling": 3,   # weakest class — false alarms are the costly error here
}

DEFAULT_CONFIRMATION = 3
SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {display_state, candidate, streak, last_seen}
# In-memory and per-session on purpose: this is transient UI-stability state,
# not session history worth persisting. It does not survive a server restart,
# which is acceptable — a restarted session simply re-adopts its first
# prediction immediately.
_sessions = {}


def required_windows(state: str) -> int:
    """How many consecutive agreeing windows are needed to display `state`."""
    return CONFIRMATION_WINDOWS.get(state, DEFAULT_CONFIRMATION)


def _evict_stale(now: float) -> None:
    stale = [key for key, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def update(uid: str, session_id: str, raw_state: str, confidence: float) -> dict:
    """
    Feed one raw prediction in, get the smoothed state out.

    The first prediction of a session is adopted immediately — there is no
    artificial "warming up" period, so the very first window behaves exactly as
    it did before smoothing existed.
    """
    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.get(key)

    if session is None:
        session = {
            "display_state": raw_state,
            "candidate": raw_state,
            "streak": 1,
            "last_seen": now,
        }
        _sessions[key] = session
    else:
        session["last_seen"] = now
        needed = required_windows(raw_state)

        if raw_state == session["candidate"]:
            # capped so a long steady session doesn't grow the counter forever
            if session["streak"] < needed:
                session["streak"] += 1
        else:
            session["candidate"] = raw_state
            session["streak"] = 1

        if raw_state != session["display_state"] and session["streak"] >= needed:
            session["display_state"] = raw_state

    return {
        "state": session["display_state"],
        "raw_state": raw_state,
        "confidence": confidence,
        "stable": session["display_state"] == raw_state,
        "streak": session["streak"],
        "required": required_windows(raw_state),
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's smoothing state (session end, or a fresh start)."""
    _sessions.pop((uid, session_id), None)

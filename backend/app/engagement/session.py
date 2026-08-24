"""
Session lifecycle and overlapping-request prevention.

Two problems in the prototype that this closes.

**Overlapping inference.** The browser sent a window every second regardless of
whether the previous one had returned. The first prediction takes ~13 s while
TensorFlow loads, so on a cold start a dozen requests would pile up, each
loading the model, each mutating the same rule-state. The rules assume they see
windows in order, once each, so out-of-order completions could corrupt a
confirmation streak or a fatigue history.

**No lifecycle.** There was no notion of a session starting or ending. Rule
state accumulated per `(uid, session_id)` and was only ever cleared by a
30-minute timeout, so a learner who closed the tab and returned inherited stale
fatigue evidence.

Both are handled here rather than in the route, so the ordering guarantee holds
however the endpoint is called.
"""

import threading
import time

from app.engagement import deep_thinking, fatigue, furrow, recovery, smoothing

SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {"started_at": float, "last_seen": float, "window_count": int}
_sessions = {}

# One lock per session. A second window for the SAME session waits for the
# first; different sessions never block each other.
_locks = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def _evict_stale(now):
    stale = [k for k, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        _clear_rule_state(*key)
        _sessions.pop(key, None)
        with _locks_guard:
            _locks.pop(key, None)


def _clear_rule_state(uid, session_id):
    """Reset every rule that keeps per-session history."""
    for module in (smoothing, fatigue, recovery, deep_thinking, furrow):
        try:
            module.reset(uid, session_id)
        except Exception:
            # A rule failing to reset must not prevent the others resetting.
            pass


def start(uid: str, session_id: str) -> dict:
    """
    Begin (or restart) a session. Clears any rule state left from a previous
    session that reused this id, so a session always starts from nothing.
    """
    now = time.time()
    _evict_stale(now)
    _clear_rule_state(uid, session_id)
    _sessions[(uid, session_id)] = {
        "started_at": now,
        "last_seen": now,
        "window_count": 0,
    }
    return {"session_id": session_id, "status": "active", "window_count": 0}


def end(uid: str, session_id: str) -> dict:
    """
    Finish a session and release its state.

    Worth calling explicitly rather than relying on the timeout: it frees the
    rule history immediately, and gives Module 8 a definite end point.
    """
    key = (uid, session_id)
    info = _sessions.pop(key, None)
    _clear_rule_state(uid, session_id)
    with _locks_guard:
        _locks.pop(key, None)

    if not info:
        return {"session_id": session_id, "status": "not_found"}

    return {
        "session_id": session_id,
        "status": "ended",
        "duration_seconds": round(time.time() - info["started_at"], 1),
        "window_count": info["window_count"],
    }


def touch(uid: str, session_id: str) -> dict:
    """Record that a window arrived, creating the session if it is the first."""
    now = time.time()
    _evict_stale(now)
    key = (uid, session_id)
    info = _sessions.get(key)
    if info is None:
        info = {"started_at": now, "last_seen": now, "window_count": 0}
        _sessions[key] = info
    info["last_seen"] = now
    info["window_count"] += 1
    return info


def process_exclusively(uid: str, session_id: str, work):
    """
    Run `work()` with no other window for the same session running concurrently.

    Serialising per session is what keeps the rules correct: they assume windows
    arrive in order, once each. Without this, two overlapping requests could
    each advance a confirmation streak from the same starting point, or append
    to a fatigue history out of order.
    """
    with _lock_for((uid, session_id)):
        return work()


def snapshot(uid: str, session_id: str):
    """Current session state, or None. Used by the status endpoint and tests."""
    info = _sessions.get((uid, session_id))
    if not info:
        return None
    return {
        "session_id": session_id,
        "status": "active",
        "started_at": info["started_at"],
        "window_count": info["window_count"],
        "age_seconds": round(time.time() - info["started_at"], 1),
    }

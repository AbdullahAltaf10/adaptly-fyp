"""
How long to stay quiet after an intervention.

Why the default is 120 seconds and not a round number someone liked
-------------------------------------------------------------------
Module 8 measures whether an intervention helped by looking at engagement in
the window after it lands:

    MetricConfig.recovery_window_seconds = 120.0
    MetricConfig.recovery_confirmation_samples = 2

If a second intervention fires inside that window, the recovery cannot be
attributed to either of them. Abdullah has already met this - `_observed_recovery`
takes a `competing_start` argument specifically to cope with overlap.

So a cooldown shorter than the recovery window does not merely annoy the
learner, it corrupts the measurement that Module 10 turns into a compliance
figure. The default matches the window rather than undercutting it.

`DEFAULT_COOLDOWN_SECONDS` should be imported from Module 8's config once
issue #45 lands and that config is reachable from the live path. Until then
this is a second copy of one number, and the comment is here so the next
person knows it must not drift.

Separately: this is in-memory, keyed by (uid, session_id), exactly like
engagement/smoothing.py. It dies on restart and breaks under multiple uvicorn
workers. Fine for single-worker development, and the same known limitation
Module 3 already carries - not a new one introduced here.
"""

import time

# Must not be lower than Module 8's recovery_window_seconds. See above.
DEFAULT_COOLDOWN_SECONDS = 120.0

SESSION_TTL_SECONDS = 1800

# (uid, session_id) -> {"last_fired": float, "last_seen": float, "count": int}
_sessions: dict[tuple[str, str], dict] = {}


def _evict_stale(now: float) -> None:
    stale = [k for k, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def is_cooling(
    uid: str,
    session_id: str,
    *,
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    now: float = None,
) -> bool:
    """
    True if an intervention fired recently enough that another would overlap
    the first one's recovery window.

    `now` is injectable so tests do not have to sleep.
    """
    now = time.time() if now is None else now
    _evict_stale(now)
    session = _sessions.get((uid, session_id))
    if session is None:
        return False
    session["last_seen"] = now
    return (now - session["last_fired"]) < cooldown_seconds


def record_fired(uid: str, session_id: str, *, now: float = None) -> None:
    """Start the cooldown. Call this when an intervention is actually sent."""
    now = time.time() if now is None else now
    session = _sessions.setdefault(
        (uid, session_id), {"last_fired": 0.0, "last_seen": now, "count": 0}
    )
    session["last_fired"] = now
    session["last_seen"] = now
    session["count"] += 1


def fired_count(uid: str, session_id: str) -> int:
    session = _sessions.get((uid, session_id))
    return session["count"] if session else 0


def reset(uid: str, session_id: str) -> None:
    """Drop a session's cooldown state - session end, or a fresh start."""
    _sessions.pop((uid, session_id), None)

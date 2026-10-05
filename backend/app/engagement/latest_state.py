"""The most recent engagement state reported for each session, for Module 5.

Scope 6.6 says the assistant "already knows ... how the session is going. The
user never needs to provide this information." Until now the assistant knew the
document and the chunk and nothing about the learner's state.

**It is read from the server, never taken from the request.** The assistant's
request body already carries a `session_context`, but that comes from the
browser and the prompt rightly treats it as untrusted. Engagement state is
different: it steers how the model addresses the learner, so it must come from
where it was actually measured. This is the same reason Module 4 refuses to let
the client report how badly it is struggling.

Deliberately small and separate from `smoothing.py`, which holds only the
model's smoothed class. The state worth telling the assistant about is the
final one, after the fatigue and recovery rules have had their say, and that
is only known at the end of the analyze route.

In-memory and per-process, like the smoothing state it sits beside: transient
context for a live conversation, not history. A restart loses it, and an
assistant with no state simply answers in its normal style, which is the safe
direction to fail in.
"""

import time

# Analyze runs about once a second (a sliding 10-frame window; see
# frontend/src/engagement/useEngagementCapture.js), so a minute without a new
# state means the capture has stopped, not that nothing changed. A state older
# than this describes a moment the learner has already moved on from, and
# acting on it would be worse than acting on nothing.
MAX_AGE_SECONDS = 60.0
SESSION_TTL_SECONDS = 1800.0

# (uid, session_id) -> (state, recorded_at)
_latest: dict[tuple[str, str], tuple[str, float]] = {}


def _evict_stale(now: float) -> None:
    stale = [key for key, (_, at) in _latest.items() if now - at > SESSION_TTL_SECONDS]
    for key in stale:
        del _latest[key]


def record(uid: str, session_id: str, state: str, *, now: float | None = None) -> None:
    """Remember the state just reported. Never raises: this is a side channel."""
    try:
        moment = time.monotonic() if now is None else now
        _evict_stale(moment)
        _latest[(uid, session_id)] = (state, moment)
    except Exception:  # noqa: BLE001 - must never disturb the analyze endpoint
        pass


def get(uid: str, session_id: str, *, now: float | None = None) -> str | None:
    """The learner's current state, or None when unknown or out of date.

    Keyed on the caller's own uid as well as the session id, so one learner's
    state can never reach another learner's conversation.
    """
    entry = _latest.get((uid, session_id))
    if entry is None:
        return None
    state, at = entry
    moment = time.monotonic() if now is None else now
    if moment - at > MAX_AGE_SECONDS:
        return None
    return state


def clear(uid: str, session_id: str) -> None:
    """Forget a session's state when it ends."""
    _latest.pop((uid, session_id), None)

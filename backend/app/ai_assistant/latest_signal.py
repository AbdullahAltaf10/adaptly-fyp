"""The most recent difficulty a learner expressed in conversation, for Module 4.

Scope 6.5: "Every user message is also analyzed for emotional signals such as
confusion or frustration ... which are **passed to the central AI layer as
high-priority signals**."

The classification half was already there (`signals.py`). The passing half was
not: `classify_conversational_signal` ran on every message, the result went
into the assistant's own prompt, and then nothing else ever saw it. Its own
docstring described the precedence order as being "for a future downstream
support layer". This is that layer's side of it.

Why Module 4 rather than Module 6
---------------------------------
The central layer scope 6.6 describes is Module 6, which does not exist yet.
But `decider.py` was built so that Module 6 arrives as a second implementation
of an interface Module 4 already uses, reading the same `Signals`. So the
honest place for this today is that `Signals` object: it reaches the policy
that actually decides things now, and it is the same field Module 6 will read
when it lands. The alternative - holding the signal until Module 6 exists -
means a learner can type "I don't understand any of this" and have the system
that is watching them take no notice.

What "high priority" means here, concretely
-------------------------------------------
It lowers the dwell gate, exactly the way an HR-tagged critical section does.
It does **not** manufacture an intervention on its own. A learner saying they
are confused is strong evidence that they are struggling, but it is not
evidence about *which* paragraph or *when*, and a policy that fired on the
words alone would interrupt someone who had already worked it out by the time
they finished typing.

Expiry matters more here than for engagement state
--------------------------------------------------
An engagement reading describes a moment. A sentence a learner typed describes
a moment too, but it feels permanent, and treating it as still true twenty
minutes later would have the system quietly over-helping someone who moved on
long ago. `MAX_AGE_SECONDS` is deliberately generous enough to cover reading
the answer and trying again, and no more.

In-memory and per-process, like `latest_state`. A restart loses it and the
policy simply behaves as it did before, which is the safe direction to fail in.
"""

import time

# Long enough to cover reading the assistant's answer and going back to the
# passage; short enough that it cannot follow a learner around a whole session.
MAX_AGE_SECONDS = 300.0
SESSION_TTL_SECONDS = 1800.0

# Signals worth passing on. "neutral" is not recorded at all: absence already
# means "nothing expressed", and storing neutral would only overwrite a real
# signal with a shrug.
FRUSTRATION = "frustration"
CONFUSION = "confusion"
PASSED_ON = (FRUSTRATION, CONFUSION)

# (uid, session_id) -> (signal, recorded_at)
_latest: dict[tuple[str, str], tuple[str, float]] = {}


def _evict_stale(now: float) -> None:
    stale = [key for key, (_, at) in _latest.items() if now - at > SESSION_TTL_SECONDS]
    for key in stale:
        del _latest[key]


def record(uid: str, session_id: str, signal: str, *, now: float | None = None) -> None:
    """Remember a difficulty the learner just expressed. Never raises.

    A neutral message leaves whatever was recorded before untouched rather
    than clearing it: someone who says "I'm lost" and then asks a plain
    follow-up question has not stopped being lost.
    """
    try:
        if signal not in PASSED_ON:
            return
        moment = time.monotonic() if now is None else now
        _evict_stale(moment)
        _latest[(uid, session_id)] = (signal, moment)
    except Exception:  # noqa: BLE001 - must never disturb the assistant endpoint
        pass


def get(uid: str, session_id: str, *, now: float | None = None) -> str | None:
    """What this learner last expressed, or None when nothing or out of date.

    Keyed on the caller's own uid as well as the session, so one learner's
    words can never influence another learner's session.
    """
    entry = _latest.get((uid, session_id))
    if entry is None:
        return None
    signal, at = entry
    moment = time.monotonic() if now is None else now
    if moment - at > MAX_AGE_SECONDS:
        return None
    return signal


def clear(uid: str, session_id: str) -> None:
    """Forget a session's signal when it ends."""
    _latest.pop((uid, session_id), None)

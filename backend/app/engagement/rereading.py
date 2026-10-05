"""
Paragraph-revisit re-reading proxy.

STATUS: implemented as a heuristic, NOT the classifier scope section 6.3
describes. That classifier - a CNN/SVM trained on the OneStop Eye Movements
dataset, watching gaze-X at sub-second resolution for a regression saccade -
remains an open, documented gap (see
sibtain-workspace/FYP_DEFENSE_GUIDE/11_RED_FLAGS_AND_HONEST_LIMITS.md, G8) for
two independent, architectural reasons: OneStop is 1000Hz lab-grade data, not
webcam-comparable, and a saccade lasts tens of milliseconds against this
pipeline's 1fps sampling rate. Neither is solved here.

What IS implemented: using data the engagement loop already has at 1fps -
which chunk the learner is on, and for how long - to detect a coarser,
paragraph-level pattern: did the learner go BACK to a paragraph they had
already moved past, and stay there long enough for it to be a real re-read
rather than a scroll-past. This is honestly weaker evidence than a real
saccade classifier, and is documented as such everywhere it is used.

Design mirrors recovery.py exactly: per-(uid, session_id) history, evicted on
a TTL, and an explicit reset() called from session.py on session start/end -
the same closed rule-module pattern every other file in this package follows.
This module knows nothing about content or intervention; it takes a plain
`chunk_order` integer and leaves looking that up to whoever calls it
(engagement/routes.py), keeping the module boundary session.py's own
docstring describes.
"""

import time

SESSION_TTL_SECONDS = 1800

# How long a re-dwell on an earlier chunk must last before it counts as a
# real re-read rather than a scroll-past glance. Estimate, not measured -
# DAiSEE has no dwell signal, same caveat as Module 4's own dwell gates.
REVISIT_MIN_DWELL_SECONDS = 8

# (uid, session_id) -> {"max_order_seen": int, "last_seen": float}
_sessions = {}


def _evict_stale(now: float) -> None:
    stale = [key for key, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def is_available() -> bool:
    """Whether re-reading detection can produce a real answer. Now: yes -
    as the dwell-revisit proxy described above, not the OneStop classifier."""
    return True


def update(uid: str, session_id: str, chunk_order, dwell_seconds: float) -> dict:
    """
    chunk_order: this window's chunk's position in the content's reading
    order (0-based), or None when the caller has none to report - a
    camera-only session, or a chunk the content lookup could not resolve.
    dwell_seconds: how long the learner has been on this chunk (same value
    Module 4's policy already receives).
    """
    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.setdefault(key, {"max_order_seen": None, "last_seen": now})
    session["last_seen"] = now

    if chunk_order is None:
        return {
            "status": "available",
            "detected": False,
            "confidence": None,
            "reason": "No chunk order reported for this window.",
        }

    max_seen = session["max_order_seen"]
    is_revisit = (
        max_seen is not None
        and chunk_order < max_seen
        and dwell_seconds >= REVISIT_MIN_DWELL_SECONDS
    )

    # A window only counts as "having reached" a chunk if the learner
    # actually dwelled there - a quick scroll-past that never lingers must
    # not raise the high-water mark, or reading normally afterwards from an
    # earlier chunk would be misread as a revisit of ground never really
    # covered.
    reached_chunk = dwell_seconds >= REVISIT_MIN_DWELL_SECONDS
    if reached_chunk and (max_seen is None or chunk_order > max_seen):
        session["max_order_seen"] = chunk_order

    if is_revisit:
        # How far back, relative to how far the learner had progressed -
        # going back to paragraph 0 after reaching paragraph 10 is stronger
        # evidence than going back one paragraph out of two.
        distance = max_seen - chunk_order
        confidence = min(1.0, distance / max(1, max_seen))
        return {
            "status": "available",
            "detected": True,
            "confidence": round(confidence, 3),
            "reason": (
                f"Returned to paragraph {chunk_order} after reaching "
                f"{max_seen}, and stayed {dwell_seconds:.0f}s."
            ),
        }

    return {
        "status": "available",
        "detected": False,
        "confidence": None,
        "reason": "No qualifying revisit this window.",
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's revisit history (session end, or after recalibration)."""
    _sessions.pop((uid, session_id), None)

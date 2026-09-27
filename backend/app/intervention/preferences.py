"""What has and has not worked for this learner, read from their learning profile.

Scope section 6.1: "The system remembers which types of support worked well for
each user and uses this in future sessions." Module 8 records it, and since
#97 actually builds and stores a profile at session end, but nothing consumed
it: every learner was offered the same response whatever had happened before.

**The design constraint is that this can only make support gentler, never
pushier.** `policy.py` ties each response to the evidence needed to justify it -
rewriting what someone is reading needs the strongest evidence *and* sustained
dwell, because it is the most intrusive thing this system does. A learner who
has responded well to rewriting must not therefore be rewritten to on weaker
evidence; that would trade the evidence tiers for a guess about a person. So the
only thing history is allowed to do is *avoid* a response that has demonstrably
not helped this learner, and offer something less intrusive instead.

"Demonstrably" is deliberate. Outcomes are noisy and most interventions have an
`unknown` outcome, which says nothing about whether it helped, so a type is
discouraged only on enough *evaluable* outcomes (effective + ineffective, not
unknown) and only when the rate is clearly poor.

Read from the profile Module 8 already stores, never recomputed here, and never
from the request: a client that could claim "simplification never works for me"
would be choosing its own interventions, which is the reason Module 4 does not
take dwell-critical flags or engagement state from the browser either.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# Enough evaluable outcomes that a poor rate is not a couple of unlucky tries.
MIN_EVALUABLE_OUTCOMES = 4

# At or below this share of evaluable outcomes being effective, a type is
# discouraged. Not a measured value: there is no per-learner data to measure it
# on yet. Deliberately strict, so that only a clear pattern changes behaviour.
DISCOURAGE_AT_OR_BELOW = 0.25

# Only the two types the policy can swap between. A break for tiredness and an
# offer of the assistant are never withheld on history.
DEMOTABLE_TYPES = frozenset({"simplify_content", "bullet_summary"})

# The profile changes once per session, at its end, so a short cache is enough
# and keeps a database read out of the once-per-ten-seconds analyze path.
CACHE_TTL_SECONDS = 300.0

# uid -> (expires_at, frozenset)
_cache: dict[str, tuple[float, frozenset[str]]] = {}


def discouraged_from_profile(profile) -> frozenset[str]:
    """Which demotable types have clearly not helped, from a stored profile.

    Pure. Anything malformed or missing yields the empty set, which means
    "no history changes anything" - the safe direction to fail in.
    """
    if not isinstance(profile, dict):
        return frozenset()

    discouraged = set()
    for item in profile.get("intervention_effectiveness_by_type") or []:
        try:
            kind = item["intervention_type"]
            if kind not in DEMOTABLE_TYPES:
                continue
            effective = int(item.get("effective_count") or 0)
            ineffective = int(item.get("ineffective_count") or 0)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue

        evaluable = effective + ineffective
        if evaluable < MIN_EVALUABLE_OUTCOMES:
            continue
        if effective / evaluable <= DISCOURAGE_AT_OR_BELOW:
            discouraged.add(kind)
    return frozenset(discouraged)


def _load_profile(uid: str):
    from app.analytics.persistence.learning_profiles import LearningProfileRepository
    from app.core.db import db

    return LearningProfileRepository(db).get(uid)


def discouraged_for(uid: str, *, now: float | None = None, load=None) -> frozenset[str]:
    """The types to avoid offering this learner. Never raises.

    A database problem means no personalisation, not a failed intervention:
    this sits on the analyze endpoint's path, and engagement detection works
    today.
    """
    moment = time.monotonic() if now is None else now
    cached = _cache.get(uid)
    if cached is not None and cached[0] > moment:
        return cached[1]

    try:
        # Resolved here rather than as a default argument, which would bind the
        # loader at definition time and make it impossible to substitute later.
        result = discouraged_from_profile((load or _load_profile)(uid))
    except Exception:  # noqa: BLE001 - personalisation is optional
        log.warning("could not read the learning profile for personalisation", exc_info=True)
        return frozenset()

    _cache[uid] = (moment + CACHE_TTL_SECONDS, result)
    return result


def forget(uid: str) -> None:
    """Drop a learner's cached answer so the next session sees the new profile."""
    _cache.pop(uid, None)

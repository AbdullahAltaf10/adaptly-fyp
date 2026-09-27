"""Recompute and store a learner's multi-session learning profile.

Scope section 6.8: "Over multiple sessions, a learning profile is built that
tracks patterns over time and makes each new session more personalized."

`build_learning_profile` (#63) is a pure function and was never called by
anything. `learning_profiles.save` had no caller either, and the API returns the
stored profile or a placeholder, so the store was always empty and every learner
got the placeholder. The profile was built in the sense that the code existed
and not in the sense that a learner ever had one.

This is the missing call, kept in its own module rather than added to
`finalization.py` so that file, and the per-session summary it computes, stay
exactly as they were.

**Recomputed from scratch on every session end rather than updated
incrementally.** A profile is a small aggregate over a handful of summaries, and
recomputing means it cannot drift: a summary corrected later, or a session
finalised out of order, is picked up on the next end rather than compounding an
earlier mistake. `build_learning_profile` is deterministic for the same input,
which is what makes that safe.

**Only summaries at the current `METRIC_VERSION` are used.** Summaries are keyed
on session id *and* metric version, so a session finalised under two versions
has two documents, and feeding both in would count that session twice.
"""

from __future__ import annotations

import logging
from typing import Any

from app.analytics.domain.learning_profile import build_learning_profile
from app.analytics.domain.metrics import METRIC_VERSION
from app.analytics.persistence.base import format_timestamp, utc_now

logger = logging.getLogger(__name__)

# A profile describes patterns over time, not a lifetime ledger. Bounding it keeps
# the recompute cheap for a heavy user and stops sessions from years ago
# outweighing what the learner is like now.
MAX_SESSIONS = 100


def refresh_learning_profile(user_id: str, repositories: Any, *, now: Any = None) -> dict | None:
    """Rebuild and save the profile. Returns it, or None when there is nothing to build.

    Raises whatever the repositories raise: the failure-safe wrapper lives at the
    call site (``session_lifecycle``), the same split ``finalize_session`` uses.
    """
    documents = repositories.session_analytics.list_by_user(user_id)
    summaries = [
        document["summary"]
        for document in documents
        if document.get("metric_version") == METRIC_VERSION and document.get("summary")
    ]
    if not summaries:
        return None

    # list_by_user is oldest-first; keep the most recent MAX_SESSIONS.
    summaries = summaries[-MAX_SESSIONS:]

    computed_at = format_timestamp(now or utc_now())
    profile = build_learning_profile(user_id, summaries, computed_at=computed_at)
    repositories.learning_profiles.save(profile, now=now)
    return profile


def refresh_learning_profile_safely(user_id: str, repositories: Any) -> None:
    """Refresh without ever raising: this runs on the end-of-session path.

    A failure costs the learner nothing they can see - the profile is one
    session out of date until the next end - so it is logged and swallowed.
    """
    try:
        refresh_learning_profile(user_id, repositories)
    except Exception:  # noqa: BLE001 - must never break ending a session
        logger.exception("Module 8 learning-profile refresh failed for user_id=%s", user_id)

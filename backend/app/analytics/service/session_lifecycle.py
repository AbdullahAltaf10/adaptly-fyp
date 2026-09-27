"""Failure-safe hooks connecting Module 3's session lifecycle
(``app.engagement.routes``) to Module 8's own session record and
finalization (Issue #82 -- "Run Module 8 finalization when a session
ends").

Both functions here are called directly from ``/engagement/session/start``
and ``/engagement/session/end``. Neither may ever raise: ending or starting
a session is a real-time, learner-facing action, and an unreachable
database or a bug in analytics must not take it down. Every failure is
logged and swallowed, exactly like Module 4's own ``intervention/store.py``
and Module 3's own ``session.py::_clear_rule_state`` already do for the
same reason.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _repositories():
    from app.analytics.persistence.client import get_database
    from app.analytics.service.finalization import AnalyticsRepositories

    return AnalyticsRepositories.from_database(get_database())


def create_session_safely(uid: str, session_id: str, content_id: str | None) -> None:
    """Create (or refresh) Module 8's own session record at session start.

    No-ops when ``content_id`` is missing. Module 8's session contract
    (``shared/contracts/session.schema.json``) requires ``content_id``, so a
    record without one would violate the same contract Module 8's own
    finalization already treats as authoritative -- silently writing an
    invalid record would just move today's "no record exists" gap into
    a "an invalid record exists" gap.

    ``/engagement/session/start``'s request body does not send
    ``content_id`` on develop today; this only takes effect once the
    frontend is updated to send it (see the linked issue's "Known
    limitation").
    """

    if not content_id:
        return
    try:
        from app.analytics.persistence.base import format_timestamp, utc_now

        repositories = _repositories()
        repositories.sessions.upsert_session(
            {
                "schema_version": "1.0",
                "session_id": session_id,
                "user_id": uid,
                "content_id": content_id,
                "status": "active",
                "started_at": format_timestamp(utc_now()),
            }
        )
    except Exception:  # noqa: BLE001 - must never break starting a session
        logger.exception(
            "Module 8 session-record creation failed for session_id=%s", session_id
        )


def finalize_session_safely(uid: str, session_id: str) -> None:
    """Run Module 8 finalization at session end. Never raises.

    Idempotent by construction: ``finalize_session`` itself already treats
    an already-completed session as a no-op (returns the existing summary
    rather than recomputing), so calling this twice for the same session
    (e.g. a retried request) is safe.
    """

    try:
        from app.analytics.service.finalization import finalize_session

        repositories = _repositories()
        finalize_session(session_id, uid, repositories)
    except Exception:  # noqa: BLE001 - must never break ending a session
        logger.exception("Module 8 finalization failed for session_id=%s", session_id)

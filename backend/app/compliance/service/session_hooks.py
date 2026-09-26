"""Failure-safe hook connecting session end (``app.engagement.routes``) to
Module 10's compliance-report generation (Issue #76 -- "Auto-generate a
compliance report at session end").

Mirrors Module 8's own ``analytics/service/session_lifecycle.py`` exactly:
this may never raise. Ending a session is a real-time, learner-facing
action, and a database problem or a bug in compliance-report generation
must not take it down -- every failure is logged and swallowed, the same
way ``finalize_session_safely`` already does for Module 8's own
finalization, which this hook is meant to run immediately after.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _repositories():
    from backend.app.analytics.persistence.client import get_database as get_analytics_database
    from backend.app.compliance.persistence.client import get_database as get_compliance_database
    from backend.app.compliance.service.generation import ComplianceRepositories

    return ComplianceRepositories.from_database(
        get_analytics_database(), get_compliance_database()
    )


def generate_report_safely(user_id: str, session_id: str) -> None:
    """Generate a compliance report for one session at session end. Never raises.

    Idempotent by construction: ``generate_report`` itself already treats an
    existing report as the answer (returns it unchanged rather than
    recalculating), and its persistence is insert-only (see
    ``ComplianceReportRepository.save``), so calling this twice for the same
    session -- a retried ``/session/end`` request, or a session that already
    had a report generated on demand via the dashboard's own "Generate
    report" button -- can never create a duplicate or a second, different
    report.

    Also silently no-ops (not an error) when Module 8's finalization hasn't
    produced a summary yet, or hasn't run at all -- ``generate_report``
    already reports that as ``outcome="no_summary"`` rather than raising, so
    there is nothing extra to swallow there; this function's own try/except
    exists for real failures (an unreachable database, a bug in report
    building), not for that expected, already-handled case.
    """

    try:
        from backend.app.compliance.service.generation import (
            SessionAccessDeniedError,
            SessionNotFoundError,
            generate_report,
        )

        repositories = _repositories()
        generate_report(session_id, user_id, repositories)
    except (SessionNotFoundError, SessionAccessDeniedError):
        # Same non-leaking posture as the API layer: a session that doesn't
        # exist (yet) or doesn't belong to this user is not a system failure
        # worth logging as one -- just nothing to generate a report for.
        logger.info(
            "Module 10 compliance-report generation skipped for session_id=%s "
            "(session not found or not owned by this user)",
            session_id,
        )
    except Exception:  # noqa: BLE001 - must never break ending a session
        logger.exception(
            "Module 10 compliance-report generation failed for session_id=%s",
            session_id,
        )

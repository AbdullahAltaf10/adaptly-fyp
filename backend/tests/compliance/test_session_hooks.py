"""Tests for the failure-safe session-end hook (Issue #76).

Mirrors ``backend/tests/analytics/test_session_lifecycle.py``'s own pattern
for Module 8's ``finalize_session_safely`` -- this is that same shape of
test for Module 10's ``generate_report_safely``.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import mongomock

from backend.app.analytics.service.finalization import (
    AnalyticsRepositories,
    finalize_session,
)
from backend.app.compliance.service import session_hooks
from backend.app.compliance.service.generation import ComplianceRepositories
from backend.tests.analytics.fixtures import fixture, timestamp


def _repositories(database) -> ComplianceRepositories:
    return ComplianceRepositories.from_database(database, database)


def _seed_finalized_session(database, *, session_id: str = "session-1", user_id: str = "user-1"):
    """Seeds a fully finalized Module 8 session, the way ``test_api.py``'s
    own helper does -- a real, finalized session with a computed summary is
    the precondition ``generate_report`` needs to do anything other than
    no-op with ``outcome="no_summary"``.
    """

    data = fixture("normal_completed_session")
    session_data = data["session"]
    session_data["session_id"] = session_id
    session_data["user_id"] = user_id
    session_data["status"] = "active"
    session_data["ended_at"] = None
    session_data["duration_seconds"] = None
    for events in (data["engagement_events"], data["intervention_events"], data["assistant_events"]):
        for event in events:
            event["session_id"] = session_id
            event["user_id"] = user_id

    analytics_repositories = AnalyticsRepositories.from_database(database)
    analytics_repositories.sessions.upsert_session(session_data)
    analytics_repositories.engagement_events.insert_events(data["engagement_events"])
    analytics_repositories.intervention_events.insert_events(data["intervention_events"])
    analytics_repositories.assistant_events.insert_events(data["assistant_events"])
    for chunk in data["chunk_context"]:
        analytics_repositories.chunk_progress.upsert_progress(
            {
                "session_id": session_id,
                "content_id": session_data["content_id"],
                "chunk_id": chunk["chunk_id"],
                "is_critical": chunk["is_critical"],
                "status": "completed" if chunk["completed"] else "in_progress",
            }
        )
    finalize_session(session_id, user_id, analytics_repositories, now=timestamp(60))


class GenerateReportSafelyTests(unittest.TestCase):
    def test_calls_generate_report_with_the_right_user_and_session(self):
        captured = {}

        def fake_generate_report(session_id, requesting_user_id, repositories):
            captured["session_id"] = session_id
            captured["requesting_user_id"] = requesting_user_id
            return None

        database = mongomock.MongoClient()["adaptly_test"]
        with patch.object(session_hooks, "_repositories", return_value=_repositories(database)):
            with patch(
                "backend.app.compliance.service.generation.generate_report",
                side_effect=fake_generate_report,
            ):
                session_hooks.generate_report_safely("user-1", "session-1")

        self.assertEqual(captured["session_id"], "session-1")
        self.assertEqual(captured["requesting_user_id"], "user-1")

    def test_swallows_any_error_from_building_repositories(self):
        with patch.object(
            session_hooks, "_repositories", side_effect=RuntimeError("db unreachable")
        ):
            try:
                session_hooks.generate_report_safely("user-1", "session-1")
            except Exception as error:  # pragma: no cover - the test itself is the assertion
                self.fail(f"generate_report_safely raised {error!r} instead of swallowing it")

    def test_swallows_errors_raised_by_generate_report_itself(self):
        database = mongomock.MongoClient()["adaptly_test"]
        with patch.object(session_hooks, "_repositories", return_value=_repositories(database)):
            with patch(
                "backend.app.compliance.service.generation.generate_report",
                side_effect=RuntimeError("unexpected failure"),
            ):
                try:
                    session_hooks.generate_report_safely("user-1", "session-1")
                except Exception as error:  # pragma: no cover
                    self.fail(
                        f"generate_report_safely raised {error!r} instead of swallowing it"
                    )

    def test_silently_skips_a_session_that_does_not_exist(self):
        """No session record at all: generate_report raises SessionNotFoundError.
        That's an expected, non-failure outcome (nothing to generate a report
        for yet -- Module 8 hasn't created the session record), not a bug to
        log as an exception.
        """

        database = mongomock.MongoClient()["adaptly_test"]
        with patch.object(session_hooks, "_repositories", return_value=_repositories(database)):
            try:
                session_hooks.generate_report_safely("user-1", "session-that-does-not-exist")
            except Exception as error:  # pragma: no cover
                self.fail(f"generate_report_safely raised {error!r} instead of swallowing it")

        # And, correctly, nothing was generated.
        stored = _repositories(database).compliance_reports.get("session-that-does-not-exist")
        self.assertIsNone(stored)

    def test_a_full_finalize_then_generate_flow_produces_exactly_one_report(self):
        """The scenario `/session/end` now drives: Module 8 finalizes the
        session, then this hook runs immediately after. Confirms real data
        flows end to end into a stored compliance report, not just that the
        function calls don't raise.
        """

        database = mongomock.MongoClient()["adaptly_test"]
        _seed_finalized_session(database, session_id="session-1", user_id="user-1")

        with patch.object(session_hooks, "_repositories", return_value=_repositories(database)):
            session_hooks.generate_report_safely("user-1", "session-1")

        stored = _repositories(database).compliance_reports.get("session-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["report"]["session_id"], "session-1")
        self.assertEqual(database["compliance_reports"].count_documents({}), 1)

    def test_calling_it_twice_never_creates_a_duplicate_or_a_different_report(self):
        """Idempotency (Issue #76 acceptance criteria): a retried
        `/session/end`, or a session that already had its report generated
        on demand via the dashboard, must never produce a second report.
        """

        database = mongomock.MongoClient()["adaptly_test"]
        _seed_finalized_session(database, session_id="session-1", user_id="user-1")

        with patch.object(session_hooks, "_repositories", return_value=_repositories(database)):
            session_hooks.generate_report_safely("user-1", "session-1")
            first = _repositories(database).compliance_reports.get("session-1")
            session_hooks.generate_report_safely("user-1", "session-1")
            second = _repositories(database).compliance_reports.get("session-1")

        self.assertEqual(first["report"], second["report"])
        self.assertEqual(database["compliance_reports"].count_documents({}), 1)


if __name__ == "__main__":
    unittest.main()

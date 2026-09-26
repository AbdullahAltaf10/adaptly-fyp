"""Tests for the failure-safe session-lifecycle hooks (Issue #82)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import mongomock

from backend.app.analytics.service import session_lifecycle
from backend.app.analytics.service.finalization import AnalyticsRepositories


def _repositories() -> AnalyticsRepositories:
    database = mongomock.MongoClient()["adaptly_test"]
    return AnalyticsRepositories.from_database(database)


class CreateSessionSafelyTests(unittest.TestCase):
    def test_creates_a_module_8_session_record_when_content_id_is_given(self):
        repositories = _repositories()
        with patch.object(session_lifecycle, "_repositories", return_value=repositories):
            session_lifecycle.create_session_safely("user-1", "session-1", "content-1")

        stored = repositories.sessions.get("session-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["user_id"], "user-1")
        self.assertEqual(stored["content_id"], "content-1")
        self.assertEqual(stored["status"], "active")
        self.assertIn("started_at", stored)

    def test_no_ops_when_content_id_is_missing(self):
        repositories = _repositories()
        with patch.object(session_lifecycle, "_repositories", return_value=repositories):
            session_lifecycle.create_session_safely("user-1", "session-1", None)

        self.assertIsNone(repositories.sessions.get("session-1"))

    def test_swallows_any_error_instead_of_raising(self):
        with patch.object(
            session_lifecycle, "_repositories", side_effect=RuntimeError("db unreachable")
        ):
            try:
                session_lifecycle.create_session_safely("user-1", "session-1", "content-1")
            except Exception as error:  # pragma: no cover - the test itself is the assertion
                self.fail(f"create_session_safely raised {error!r} instead of swallowing it")


class FinalizeSessionSafelyTests(unittest.TestCase):
    def test_calls_finalize_session_with_the_right_user_and_session(self):
        captured = {}

        def fake_finalize_session(session_id, requesting_user_id, repositories):
            captured["session_id"] = session_id
            captured["requesting_user_id"] = requesting_user_id
            return None

        with patch.object(session_lifecycle, "_repositories", return_value=_repositories()):
            with patch(
                "backend.app.analytics.service.finalization.finalize_session",
                side_effect=fake_finalize_session,
            ):
                session_lifecycle.finalize_session_safely("user-1", "session-1")

        self.assertEqual(captured["session_id"], "session-1")
        self.assertEqual(captured["requesting_user_id"], "user-1")

    def test_swallows_any_error_instead_of_raising(self):
        with patch.object(
            session_lifecycle, "_repositories", side_effect=RuntimeError("db unreachable")
        ):
            try:
                session_lifecycle.finalize_session_safely("user-1", "session-1")
            except Exception as error:  # pragma: no cover - the test itself is the assertion
                self.fail(f"finalize_session_safely raised {error!r} instead of swallowing it")

    def test_swallows_errors_raised_by_finalize_session_itself(self):
        with patch.object(session_lifecycle, "_repositories", return_value=_repositories()):
            with patch(
                "backend.app.analytics.service.finalization.finalize_session",
                side_effect=RuntimeError("unexpected failure"),
            ):
                try:
                    session_lifecycle.finalize_session_safely("user-1", "session-1")
                except Exception as error:  # pragma: no cover
                    self.fail(
                        f"finalize_session_safely raised {error!r} instead of swallowing it"
                    )


if __name__ == "__main__":
    unittest.main()

"""Tests for Module 8 session finalization (Issue #28).

Uses mongomock (via AnalyticsRepositories.from_database) so no live MongoDB
is required, and reuses the Issue #26 contract-shaped fixtures so seeded
events are realistic.
"""

from __future__ import annotations

import unittest
from typing import Any

import mongomock

from backend.app.analytics.service.finalization import (
    AnalyticsRepositories,
    SessionAccessDeniedError,
    SessionNotFoundError,
    finalize_session,
)
from backend.tests.analytics.fixtures import fixture, intervention, timestamp


def _repositories() -> AnalyticsRepositories:
    database = mongomock.MongoClient()["adaptly_test"]
    return AnalyticsRepositories.from_database(database)


def _seed_scenario(
    repositories: AnalyticsRepositories,
    scenario: str,
    *,
    status: str = "active",
    seed_chunk_progress: bool = True,
) -> dict[str, Any]:
    data = fixture(scenario)
    session_data = data["session"]
    session_data["status"] = status
    if status != "completed":
        session_data["ended_at"] = None
        session_data["duration_seconds"] = None
    repositories.sessions.upsert_session(session_data)
    repositories.engagement_events.insert_events(data["engagement_events"])
    repositories.intervention_events.insert_events(data["intervention_events"])
    repositories.assistant_events.insert_events(data["assistant_events"])
    if seed_chunk_progress:
        for chunk in data["chunk_context"]:
            repositories.chunk_progress.upsert_progress(
                {
                    "session_id": session_data["session_id"],
                    "content_id": session_data["content_id"],
                    "chunk_id": chunk["chunk_id"],
                    "is_critical": chunk["is_critical"],
                    "status": "completed" if chunk["completed"] else "in_progress",
                }
            )
    return session_data


class SuccessfulFinalizationTests(unittest.TestCase):
    def test_finalizes_session_and_computes_summary(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")

        result = finalize_session(
            "session-1", "user-1", repositories, now=timestamp(60)
        )

        self.assertEqual(result.outcome, "finalized")
        self.assertEqual(result.session["status"], "completed")
        self.assertEqual(result.session["duration_seconds"], 60)
        self.assertEqual(result.summary["session_id"], "session-1")
        self.assertEqual(result.summary["metric_version"], "1.0")

    def test_completed_session_state_is_persisted(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")

        finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        stored_session = repositories.sessions.get("session-1")
        self.assertEqual(stored_session["status"], "completed")
        self.assertEqual(stored_session["ended_at"], timestamp(60))
        stored_summary = repositories.session_analytics.get("session-1", "1.0")
        self.assertIsNotNone(stored_summary)
        self.assertEqual(stored_summary["insight_report_status"], "pending")

    def test_no_interventions_scenario_finalizes_cleanly(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "no_interventions")

        result = finalize_session(
            "session-1", "user-1", repositories, now=timestamp(60)
        )

        self.assertEqual(result.outcome, "finalized")
        self.assertEqual(result.summary["intervention_metrics"]["total_count"], 0)

    def test_sparse_engagement_scenario_flags_data_quality(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "sparse_missing_engagement")

        result = finalize_session(
            "session-1", "user-1", repositories, now=timestamp(60)
        )

        self.assertEqual(result.outcome, "finalized")
        self.assertFalse(result.summary["data_quality"]["has_sufficient_data"])
        self.assertTrue(result.summary["data_quality"]["flags"])

    def test_missing_optional_data_still_finalizes_with_flags(self) -> None:
        repositories = _repositories()
        _seed_scenario(
            repositories,
            "no_assistant_usage",
            seed_chunk_progress=False,
        )

        result = finalize_session(
            "session-1", "user-1", repositories, now=timestamp(60)
        )

        self.assertEqual(result.outcome, "finalized")
        self.assertEqual(result.summary["assistant_usage"]["total_event_count"], 0)
        self.assertEqual(
            result.summary["critical_section_engagement"]["critical_section_count"], 0
        )
        self.assertIn("missing_chunk_context", result.summary["data_quality"]["flags"])


class IdempotencyTests(unittest.TestCase):
    def test_repeated_finalization_returns_existing_summary(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")

        first = finalize_session("session-1", "user-1", repositories, now=timestamp(60))
        second = finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        self.assertEqual(first.outcome, "finalized")
        self.assertEqual(second.outcome, "already_finalized")
        self.assertEqual(first.summary, second.summary)

    def test_repeated_finalization_does_not_duplicate_summary_documents(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")

        finalize_session("session-1", "user-1", repositories, now=timestamp(60))
        finalize_session("session-1", "user-1", repositories, now=timestamp(60))
        finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        stored = repositories.session_analytics.list_by_session("session-1")
        self.assertEqual(len(stored), 1)

    def test_already_completed_without_summary_self_heals(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session", status="completed")

        result = finalize_session("session-1", "user-1", repositories)

        self.assertEqual(result.outcome, "finalized")
        self.assertIsNotNone(repositories.session_analytics.get("session-1", "1.0"))


class SessionStateHandlingTests(unittest.TestCase):
    def test_missing_session_raises(self) -> None:
        repositories = _repositories()

        with self.assertRaises(SessionNotFoundError):
            finalize_session("does-not-exist", "user-1", repositories)

    def test_cross_user_access_is_denied_and_session_untouched(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")

        with self.assertRaises(SessionAccessDeniedError):
            finalize_session("session-1", "someone-else", repositories, now=timestamp(60))

        self.assertEqual(repositories.sessions.get("session-1")["status"], "active")

    def test_abandoned_session_is_rejected_not_finalized(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session", status="abandoned")

        result = finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        self.assertEqual(result.outcome, "rejected")
        self.assertEqual(result.reason_code, "session_abandoned")
        self.assertEqual(repositories.sessions.get("session-1")["status"], "abandoned")

    def test_paused_session_is_eligible_and_finalizes(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session", status="paused")

        result = finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        self.assertEqual(result.outcome, "finalized")
        self.assertEqual(result.session["status"], "completed")

    def test_created_session_is_rejected(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session", status="created")

        result = finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        self.assertEqual(result.outcome, "rejected")
        self.assertEqual(result.reason_code, "session_not_eligible")


class DurationCalculationTests(unittest.TestCase):
    def test_paused_time_is_included_in_wall_clock_duration(self) -> None:
        repositories = _repositories()
        session_data = _seed_scenario(
            repositories, "normal_completed_session", seed_chunk_progress=False
        )
        repositories.engagement_events._collection.delete_many({})

        result = finalize_session(
            "session-1", "user-1", repositories, now=timestamp(600)
        )

        self.assertEqual(result.outcome, "finalized")
        self.assertEqual(result.summary["duration_seconds"], 600)
        self.assertEqual(
            result.summary["engagement_distribution"]["unknown"]["duration_seconds"],
            600,
        )

    def test_missing_start_time_fails_safely_without_corrupting_session(self) -> None:
        repositories = _repositories()
        repositories.sessions.upsert_session(
            {
                "schema_version": "1.0",
                "session_id": "session-bad",
                "user_id": "user-1",
                "content_id": "content-1",
                "status": "active",
                "started_at": "not-a-timestamp",
            }
        )

        result = finalize_session("session-bad", "user-1", repositories)

        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.reason_code, "invalid_start_time")
        self.assertEqual(repositories.sessions.get("session-bad")["status"], "active")

    def test_end_before_start_fails_safely_without_corrupting_session(self) -> None:
        repositories = _repositories()
        repositories.sessions.upsert_session(
            {
                "schema_version": "1.0",
                "session_id": "session-bad-order",
                "user_id": "user-1",
                "content_id": "content-1",
                "status": "active",
                "started_at": timestamp(100),
            }
        )

        result = finalize_session(
            "session-bad-order", "user-1", repositories, now=timestamp(0)
        )

        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.reason_code, "invalid_timestamp_order")
        self.assertEqual(
            repositories.sessions.get("session-bad-order")["status"], "active"
        )


class FailureHandlingTests(unittest.TestCase):
    def test_failed_metric_computation_does_not_corrupt_session_or_save_summary(
        self,
    ) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")
        cross_user_event = intervention(20, intervention_number=99)
        cross_user_event["user_id"] = "someone-else"
        repositories.intervention_events.insert_events([cross_user_event])

        result = finalize_session(
            "session-1", "user-1", repositories, now=timestamp(60)
        )

        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.reason_code, "analytics_computation_failed")
        self.assertEqual(repositories.sessions.get("session-1")["status"], "active")
        self.assertIsNone(repositories.session_analytics.get("session-1", "1.0"))

    def test_retry_succeeds_after_bad_data_is_removed(self) -> None:
        repositories = _repositories()
        _seed_scenario(repositories, "normal_completed_session")
        cross_user_event = intervention(20, intervention_number=99)
        cross_user_event["user_id"] = "someone-else"
        repositories.intervention_events.insert_events([cross_user_event])

        finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        repositories.intervention_events._collection.delete_one(
            {"_id": "intervention-99"}
        )
        retry = finalize_session("session-1", "user-1", repositories, now=timestamp(60))

        self.assertEqual(retry.outcome, "finalized")


if __name__ == "__main__":
    unittest.main()

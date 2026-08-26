"""API tests for Module 8's endpoints (Issue #29).

Uses FastAPI's TestClient with dependency overrides so no real MongoDB
connection or real authentication is needed: ``get_repositories`` is
overridden with a mongomock-backed instance, and ``get_current_user_id`` is
overridden with a fixed user id (except where the test is specifically about
the auth dependency itself).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import mongomock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.analytics.api.deps import get_repositories
from backend.app.analytics.api.routes import router
from backend.app.analytics.service.finalization import (
    AnalyticsRepositories,
    finalize_session,
)
from backend.app.api.deps import get_current_user_id
from backend.tests.analytics.fixtures import fixture, timestamp
from backend.tests.analytics.test_metrics import assert_schema_match

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _schema(name: str) -> dict[str, Any]:
    path = REPOSITORY_ROOT / "shared" / "contracts" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _repositories() -> AnalyticsRepositories:
    database = mongomock.MongoClient()["adaptly_test"]
    return AnalyticsRepositories.from_database(database)


def _build_app(repositories: AnalyticsRepositories, user_id: str | None = "user-1") -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repositories] = lambda: repositories
    if user_id is not None:
        app.dependency_overrides[get_current_user_id] = lambda: user_id
    return app


def _seed_session(
    repositories: AnalyticsRepositories,
    scenario: str = "normal_completed_session",
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    status: str = "active",
) -> dict[str, Any]:
    data = fixture(scenario)
    session_data = data["session"]
    if session_id is not None:
        session_data["session_id"] = session_id
    if user_id is not None:
        session_data["user_id"] = user_id
    for events in (
        data["engagement_events"],
        data["intervention_events"],
        data["assistant_events"],
    ):
        for event in events:
            event["session_id"] = session_data["session_id"]
            if user_id is not None:
                event["user_id"] = user_id
    session_data["status"] = status
    if status != "completed":
        session_data["ended_at"] = None
        session_data["duration_seconds"] = None
    repositories.sessions.upsert_session(session_data)
    repositories.engagement_events.insert_events(data["engagement_events"])
    repositories.intervention_events.insert_events(data["intervention_events"])
    repositories.assistant_events.insert_events(data["assistant_events"])
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


def _seed_and_finalize(
    repositories: AnalyticsRepositories,
    scenario: str = "normal_completed_session",
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    now: str = timestamp(60),
) -> dict[str, Any]:
    session_data = _seed_session(
        repositories, scenario, session_id=session_id, user_id=user_id, status="active"
    )
    result = finalize_session(
        session_data["session_id"],
        session_data["user_id"],
        repositories,
        now=now,
    )
    assert result.outcome == "finalized", result
    return result.session


class SessionAnalyticsEndpointTests(unittest.TestCase):
    def test_successful_retrieval_returns_full_payload(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        client = TestClient(_build_app(repositories))

        response = client.get("/api/sessions/session-1/analytics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "session-1")
        self.assertEqual(body["metric_version"], "1.0")
        self.assertIn("timeline_segments", body)
        self.assertIn("engagement_distribution", body)
        self.assertIn("recovery_metrics", body)
        self.assertIn("assistant_usage", body)
        self.assertIn("data_quality", body)
        self.assertEqual(body["insight_report"], {"status": "pending", "report_text": None})

    def test_cross_user_access_is_denied_as_404(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        client = TestClient(_build_app(repositories, user_id="someone-else"))

        response = client.get("/api/sessions/session-1/analytics")

        self.assertEqual(response.status_code, 404)

    def test_unknown_session_is_404_identically_to_cross_user(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        owner_client = TestClient(_build_app(repositories, user_id="someone-else"))
        missing_client = TestClient(_build_app(repositories))

        cross_user_response = owner_client.get("/api/sessions/session-1/analytics")
        missing_response = missing_client.get("/api/sessions/does-not-exist/analytics")

        self.assertEqual(cross_user_response.status_code, missing_response.status_code)
        self.assertEqual(cross_user_response.json(), missing_response.json())

    def test_active_session_is_not_exposed_as_final_analytics(self) -> None:
        repositories = _repositories()
        _seed_session(repositories, status="active")
        client = TestClient(_build_app(repositories))

        response = client.get("/api/sessions/session-1/analytics")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["reason_code"], "session_not_completed")

    def test_missing_summary_for_completed_session_is_409(self) -> None:
        repositories = _repositories()
        session_data = _seed_session(repositories, status="completed")
        # status="completed" but no finalize_session call means no summary was ever saved.
        client = TestClient(_build_app(repositories))

        response = client.get(f"/api/sessions/{session_data['session_id']}/analytics")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["reason_code"], "analytics_summary_missing")

    def test_missing_auth_header_is_401(self) -> None:
        repositories = _repositories()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_repositories] = lambda: repositories
        client = TestClient(app)  # get_current_user_id NOT overridden

        response = client.get("/api/sessions/session-1/analytics")

        self.assertEqual(response.status_code, 401)


class SessionHistoryEndpointTests(unittest.TestCase):
    def _seed_three_sessions(self, repositories: AnalyticsRepositories) -> None:
        for index, offset in enumerate((0, 100, 200)):
            _seed_and_finalize(
                repositories,
                "no_interventions",
                session_id=f"session-{index + 1}",
                now=timestamp(60 + offset),
            )

    def test_history_is_ordered_most_recent_completed_first(self) -> None:
        repositories = _repositories()
        self._seed_three_sessions(repositories)
        client = TestClient(_build_app(repositories))

        response = client.get("/api/analytics/sessions")

        ids = [item["session_id"] for item in response.json()["items"]]
        self.assertEqual(ids, ["session-3", "session-2", "session-1"])

    def test_pagination_limit_and_offset(self) -> None:
        repositories = _repositories()
        self._seed_three_sessions(repositories)
        client = TestClient(_build_app(repositories))

        response = client.get("/api/analytics/sessions", params={"limit": 1, "offset": 1})

        body = response.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["session_id"], "session-2")
        self.assertEqual(
            body["pagination"],
            {"limit": 1, "offset": 1, "returned_count": 1, "total_count": 3},
        )

    def test_invalid_pagination_input_is_422(self) -> None:
        repositories = _repositories()
        client = TestClient(_build_app(repositories))

        zero_limit = client.get("/api/analytics/sessions", params={"limit": 0})
        negative_offset = client.get("/api/analytics/sessions", params={"offset": -1})
        too_large_limit = client.get("/api/analytics/sessions", params={"limit": 1000})

        self.assertEqual(zero_limit.status_code, 422)
        self.assertEqual(negative_offset.status_code, 422)
        self.assertEqual(too_large_limit.status_code, 422)

    def test_empty_history_returns_empty_list_not_an_error(self) -> None:
        repositories = _repositories()
        client = TestClient(_build_app(repositories))

        response = client.get("/api/analytics/sessions")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["pagination"]["total_count"], 0)

    def test_history_items_exclude_raw_timeline_segments(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        client = TestClient(_build_app(repositories))

        response = client.get("/api/analytics/sessions")

        self.assertNotIn("timeline_segments", response.json()["items"][0])

    def test_history_never_includes_another_users_sessions(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories, session_id="session-mine")
        _seed_and_finalize(
            repositories,
            "no_interventions",
            session_id="session-other",
            user_id="user-2",
        )
        client = TestClient(_build_app(repositories, user_id="user-1"))

        response = client.get("/api/analytics/sessions")

        ids = [item["session_id"] for item in response.json()["items"]]
        self.assertEqual(ids, ["session-mine"])


class LearningProfileEndpointTests(unittest.TestCase):
    def test_returns_contract_shaped_placeholder_when_none_exists(self) -> None:
        repositories = _repositories()
        client = TestClient(_build_app(repositories))

        response = client.get("/api/analytics/learning-profile")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], "user-1")
        self.assertEqual(body["focus_trend"], "insufficient_data")
        self.assertEqual(body["sessions_analyzed"], 0)
        assert_schema_match(body, _schema("learning-profile.schema.json"))

    def test_returns_real_profile_once_one_exists(self) -> None:
        repositories = _repositories()
        real_profile = {
            "schema_version": "1.0",
            "metric_version": "1.0",
            "user_id": "user-1",
            "sessions_analyzed": 5,
            "analysis_date_range": {
                "started_at": timestamp(0),
                "ended_at": timestamp(1000),
            },
            "average_session_duration_seconds": 600,
            "average_focus_percentage": 70.0,
            "focus_trend": "improving",
            "recovery_trend": "stable",
            "intervention_effectiveness_by_type": [],
            "assistant_usage_patterns": {
                "sessions_with_assistant_use": 3,
                "average_learner_messages_per_session": 2.0,
                "typed_input_count": 4,
                "voice_input_count": 0,
                "suggested_question_count": 0,
                "preferred_input_mode": "typed",
            },
            "recurring_difficulty_areas": [],
            "effective_support_methods": [],
            "critical_section_aggregates": {
                "sections_observed": 1,
                "sessions_with_critical_sections": 1,
                "average_engagement_rate": 0.8,
                "average_focus_percentage": 75.0,
            },
            "data_quality": {
                "sessions_with_sufficient_data": 5,
                "average_event_coverage_rate": 0.9,
                "flags": [],
            },
            "computed_at": timestamp(1000),
        }
        repositories.learning_profiles.save(real_profile)
        client = TestClient(_build_app(repositories))

        response = client.get("/api/analytics/learning-profile")

        self.assertEqual(response.json()["sessions_analyzed"], 5)
        self.assertEqual(response.json()["focus_trend"], "improving")


class InsightReportRetryEndpointTests(unittest.TestCase):
    def test_retry_does_not_recompute_or_duplicate_the_summary(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        before = repositories.session_analytics.get("session-1", "1.0")
        client = TestClient(_build_app(repositories))

        response = client.post("/api/sessions/session-1/insight-report/retry")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["insight_report_status"], "pending")
        self.assertFalse(body["retried"])
        after = repositories.session_analytics.get("session-1", "1.0")
        self.assertEqual(before, after)
        self.assertEqual(len(repositories.session_analytics.list_by_session("session-1")), 1)

    def test_retry_on_incomplete_session_is_409(self) -> None:
        repositories = _repositories()
        _seed_session(repositories, status="active")
        client = TestClient(_build_app(repositories))

        response = client.post("/api/sessions/session-1/insight-report/retry")

        self.assertEqual(response.status_code, 409)

    def test_retry_on_unknown_session_is_404(self) -> None:
        repositories = _repositories()
        client = TestClient(_build_app(repositories))

        response = client.post("/api/sessions/does-not-exist/insight-report/retry")

        self.assertEqual(response.status_code, 404)

    def test_retry_when_report_already_generated_reports_nothing_to_retry(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        repositories.session_analytics.set_insight_report_status(
            "session-1", "1.0", "generated"
        )
        client = TestClient(_build_app(repositories))

        response = client.post("/api/sessions/session-1/insight-report/retry")

        body = response.json()
        self.assertEqual(body["insight_report_status"], "generated")
        self.assertIn("already exists", body["message"])


class ResponseContractCompatibilityTests(unittest.TestCase):
    def test_session_analytics_payload_matches_session_summary_contract(self) -> None:
        repositories = _repositories()
        _seed_and_finalize(repositories)
        client = TestClient(_build_app(repositories))

        response = client.get("/api/sessions/session-1/analytics")

        body = response.json()
        contract_only = {key: value for key, value in body.items() if key != "insight_report"}
        assert_schema_match(contract_only, _schema("session-summary.schema.json"))


if __name__ == "__main__":
    unittest.main()

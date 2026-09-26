"""API tests for Module 10's compliance-report endpoints (Issue #74).

Uses FastAPI's TestClient with dependency overrides, the same pattern
Module 8's own ``analytics/tests/test_api.py`` uses: ``get_repositories`` is
overridden with a mongomock-backed instance, and ``get_current_user_id``
with a fixed user id. The ``users`` collection (for HR-admin role checks)
is stubbed the same way ``backend/tests/test_user_endpoints.py`` stubs it:
monkeypatching the module-level ``db`` reference each consumer imported.
"""

from __future__ import annotations

import unittest
from typing import Any

import mongomock
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.auth.authorization as authorization
import backend.app.compliance.api.routes as compliance_routes
from app.auth.dependencies import get_current_user
from backend.app.api.deps import get_current_user_id
from backend.app.analytics.service.finalization import (
    AnalyticsRepositories,
    finalize_session,
)
from backend.app.compliance.api.deps import get_repositories
from backend.app.compliance.api.routes import router
from backend.app.compliance.service.generation import ComplianceRepositories
from backend.tests.analytics.fixtures import fixture, timestamp


def _database() -> Any:
    return mongomock.MongoClient()["adaptly_test"]


def _repositories(database: Any) -> ComplianceRepositories:
    return ComplianceRepositories.from_database(database, database)


def _build_app(
    database: Any, user_id: str | None = "user-1"
) -> tuple[FastAPI, ComplianceRepositories]:
    app_instance = FastAPI()
    app_instance.include_router(router)
    repositories = _repositories(database)
    app_instance.dependency_overrides[get_repositories] = lambda: repositories
    if user_id is not None:
        app_instance.dependency_overrides[get_current_user_id] = lambda: user_id
        # require_hr_admin (used by the list endpoint) depends on
        # get_current_user, not get_current_user_id -- both must be
        # overridden so a test caller doesn't need a real Firebase token.
        app_instance.dependency_overrides[get_current_user] = lambda: {
            "uid": user_id,
            "email": f"{user_id}@test.invalid",
        }
    return app_instance, repositories


def _set_profile(database: Any, uid: str, *, corporate_role: str | None) -> None:
    database.users.update_one(
        {"uid": uid},
        {
            "$set": {
                "uid": uid,
                "mode": "corporate" if corporate_role else "learner",
                "corporate_role": corporate_role,
            }
        },
        upsert=True,
    )


def _seed_finalized_session(
    database: Any, *, session_id: str = "session-1", user_id: str = "user-1"
) -> None:
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


class GenerateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self._reset)

    def _reset(self):
        pass

    def test_owner_can_generate_a_report(self):
        database = _database()
        _seed_finalized_session(database)
        app_instance, _ = _build_app(database, user_id="user-1")
        client = TestClient(app_instance)

        response = client.post("/api/sessions/session-1/compliance-report")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["outcome"], "generated")
        self.assertEqual(body["report"]["session_id"], "session-1")

    def test_generation_is_idempotent(self):
        database = _database()
        _seed_finalized_session(database)
        app_instance, _ = _build_app(database, user_id="user-1")
        client = TestClient(app_instance)

        first = client.post("/api/sessions/session-1/compliance-report").json()
        second = client.post("/api/sessions/session-1/compliance-report").json()
        self.assertEqual(first["report"], second["report"])
        self.assertEqual(second["outcome"], "already_exists")
        self.assertEqual(
            database["compliance_reports"].count_documents({}), 1
        )

    def test_generation_without_a_finalized_summary_returns_a_clear_error(self):
        database = _database()
        data = fixture("normal_completed_session")
        session_data = data["session"]
        session_data["status"] = "active"
        AnalyticsRepositories.from_database(database).sessions.upsert_session(session_data)
        app_instance, _ = _build_app(database, user_id=session_data["user_id"])
        client = TestClient(app_instance)

        response = client.post(f"/api/sessions/{session_data['session_id']}/compliance-report")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["reason_code"], "analytics_summary_missing")

    def test_non_owner_cannot_generate_a_report(self):
        database = _database()
        _seed_finalized_session(database)
        app_instance, _ = _build_app(database, user_id="someone-else")
        client = TestClient(app_instance)

        response = client.post("/api/sessions/session-1/compliance-report")
        self.assertEqual(response.status_code, 404)


class GetEndpointTests(unittest.TestCase):
    def setUp(self):
        authorization.db = None  # ensure a clean monkeypatch target each test
        compliance_routes.users_db = None

    def test_owner_can_fetch_their_own_report(self):
        database = _database()
        _seed_finalized_session(database)
        _set_profile(database, "user-1", corporate_role=None)
        authorization.db = database
        compliance_routes.users_db = database
        app_instance, repositories = _build_app(database, user_id="user-1")
        client = TestClient(app_instance)
        client.post("/api/sessions/session-1/compliance-report")

        response = client.get("/api/sessions/session-1/compliance-report")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], "session-1")

    def test_other_employee_is_denied(self):
        database = _database()
        _seed_finalized_session(database)
        _set_profile(database, "user-1", corporate_role=None)
        _set_profile(database, "other-employee", corporate_role="employee")
        authorization.db = database
        compliance_routes.users_db = database
        app_instance, _ = _build_app(database, user_id="user-1")
        TestClient(app_instance).post("/api/sessions/session-1/compliance-report")

        app_instance_other, _ = _build_app(database, user_id="other-employee")
        response = TestClient(app_instance_other).get("/api/sessions/session-1/compliance-report")
        self.assertEqual(response.status_code, 404)

    def test_hr_admin_can_fetch_any_report(self):
        database = _database()
        _seed_finalized_session(database)
        _set_profile(database, "user-1", corporate_role=None)
        _set_profile(database, "hr-1", corporate_role="hr_admin")
        authorization.db = database
        compliance_routes.users_db = database
        app_instance, _ = _build_app(database, user_id="user-1")
        TestClient(app_instance).post("/api/sessions/session-1/compliance-report")

        app_instance_hr, _ = _build_app(database, user_id="hr-1")
        response = TestClient(app_instance_hr).get("/api/sessions/session-1/compliance-report")
        self.assertEqual(response.status_code, 200)

    def test_missing_report_returns_a_clear_error(self):
        database = _database()
        _seed_finalized_session(database)
        _set_profile(database, "user-1", corporate_role=None)
        authorization.db = database
        compliance_routes.users_db = database
        app_instance, _ = _build_app(database, user_id="user-1")

        response = TestClient(app_instance).get("/api/sessions/session-1/compliance-report")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["reason_code"], "compliance_report_missing"
        )


class ListEndpointTests(unittest.TestCase):
    def test_hr_admin_can_list_reports(self):
        database = _database()
        _seed_finalized_session(database)
        _set_profile(database, "hr-1", corporate_role="hr_admin")
        authorization.db = database
        compliance_routes.users_db = database
        app_instance, _ = _build_app(database, user_id="user-1")
        TestClient(app_instance).post("/api/sessions/session-1/compliance-report")

        app_instance_hr, _ = _build_app(database, user_id="hr-1")
        response = TestClient(app_instance_hr).get("/api/compliance/reports")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)

    def test_non_hr_user_is_denied_the_list_endpoint(self):
        database = _database()
        _set_profile(database, "user-1", corporate_role=None)
        authorization.db = database
        compliance_routes.users_db = database
        app_instance, _ = _build_app(database, user_id="user-1")

        response = TestClient(app_instance).get("/api/compliance/reports")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()

"""
GET /engagement/calibration-status - lets the frontend decide, before a
session even starts, whether to silently auto-calibrate this learner (see
2026-09-30 audit: the pre-session "Calibrate" button only calibrates
WebGazer, not Module 3's own per-user baseline - the manual "Calibrate now"
mid-session button was the only path to it, and nothing prompted a learner
to click it. The model's own /calibrate docstring already says "without
this, attentive users are classified as distracted"). Auto-calibrating every
session regardless would needlessly churn the session id for an
already-calibrated returning learner (see useEngagementCapture.js's
runCalibration, which starts a fresh session on every calibration) - this
endpoint is what lets the frontend calibrate silently only once, on a
learner's first-ever session.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.engagement import routes as engagement_routes  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "u1", "email": "u1@t.com"}
    yield
    app.dependency_overrides.clear()


class FakeCalibrationCollection:
    def __init__(self, docs=None):
        self.docs = docs or {}

    def find_one(self, query):
        return self.docs.get(query["uid"])


def _stub_db(monkeypatch, docs=None):
    class DB:
        calibration = FakeCalibrationCollection(docs)

    monkeypatch.setattr(engagement_routes, "db", DB())


def test_a_new_learner_is_not_calibrated(monkeypatch):
    _stub_db(monkeypatch)
    response = client.get("/engagement/calibration-status")
    assert response.status_code == 200
    assert response.json() == {"calibrated": False}


def test_a_learner_with_a_stored_baseline_is_calibrated(monkeypatch):
    _stub_db(monkeypatch, {"u1": {"uid": "u1", "offset": [0.0] * 9}})
    response = client.get("/engagement/calibration-status")
    assert response.json() == {"calibrated": True}


def test_never_reports_another_learners_calibration(monkeypatch):
    _stub_db(monkeypatch, {"u2": {"uid": "u2", "offset": [0.0] * 9}})
    response = client.get("/engagement/calibration-status")
    assert response.json() == {"calibrated": False}


def test_requires_authentication():
    app.dependency_overrides.clear()
    assert client.get("/engagement/calibration-status").status_code == 401

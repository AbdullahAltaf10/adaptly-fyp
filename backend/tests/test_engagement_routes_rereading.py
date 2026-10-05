"""
Confirms chunk_order flows end-to-end: /analyze populates
gaze_regression_detected on a genuine revisit, and never on forward-only
reading. Reuses the same route-level stubbing pattern as
test_intervention_lifecycle.py's `stubbed_window` fixture (model and
calibration lookup stubbed at the route's own seams), since that fixture is
local to that file and not shared via conftest.py.

chunk_order is resolved server-side from the stored chunk (app.intervention.
content.chunk_order), the same trust boundary as is_critical - a client
cannot claim its own chunk_order, so it is never accepted as a request field
and this file stubs Module 2's content collection instead of sending one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.engagement import routes as engagement_routes  # noqa: E402
from app.engagement import rereading  # noqa: E402
from app.intervention import content  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

CONTENT_ID = "c1"


@pytest.fixture(autouse=True)
def clean_state():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "u1", "email": "u1@t.com"}
    yield
    app.dependency_overrides.clear()
    rereading.reset("u1", "rereading-route-forward")
    rereading.reset("u1", "rereading-route-revisit")


@pytest.fixture(autouse=True)
def stubbed_model(monkeypatch):
    monkeypatch.setattr(
        engagement_routes, "extract_feature_sequence", lambda frames: [[0.0] * 9] * 10
    )
    monkeypatch.setattr(
        engagement_routes, "predict",
        lambda sequence, **kwargs: {"state": "focused", "confidence": 0.9},
    )
    monkeypatch.setattr(engagement_routes.head_pose, "mean_pose", lambda raw: None)

    class NoCalibration:
        def find_one(self, query):
            return None

    class DB:
        calibration = NoCalibration()

    monkeypatch.setattr(engagement_routes, "db", DB())


@pytest.fixture(autouse=True)
def stubbed_content(monkeypatch):
    """
    Stand in for Module 2's content collection - chunk_order is read from
    here, exactly like is_critical, never trusted from the request.
    """
    doc = {
        "chunks": [
            {"chunk_id": str(order), "order": order, "text": "A passage.", "is_critical": False}
            for order in range(5)
        ]
    }

    class Content:
        def find_one(self, query, projection=None):
            return dict(doc)

    class DB:
        content = Content()

    monkeypatch.setattr(content, "db", DB())
    monkeypatch.setattr(content, "_object_id", lambda cid: cid)
    content.reset_cache()


def _analyze(session_id, chunk_order, dwell_seconds):
    return client.post(
        "/engagement/analyze",
        json={
            "frames": [{"landmarks": None} for _ in range(10)],
            "session_id": session_id,
            "content_id": CONTENT_ID,
            "chunk_id": str(chunk_order),
            "dwell_seconds": dwell_seconds,
        },
    )


def test_forward_reading_never_sets_gaze_regression_detected():
    session_id = "rereading-route-forward"
    engagement_routes.session_state.start("u1", session_id)
    for order in [0, 1, 2]:
        response = _analyze(session_id, order, dwell_seconds=10.0)
    assert response.json()["event"]["gaze_regression_detected"] is False


def test_a_qualifying_revisit_sets_gaze_regression_detected():
    session_id = "rereading-route-revisit"
    engagement_routes.session_state.start("u1", session_id)
    _analyze(session_id, 0, dwell_seconds=10.0)
    _analyze(session_id, 1, dwell_seconds=10.0)
    response = _analyze(session_id, 0, dwell_seconds=9.0)
    assert response.json()["event"]["gaze_regression_detected"] is True


def test_a_client_cannot_claim_its_own_chunk_order():
    """
    Sending chunk_order in the request body must change nothing - the field
    does not exist on AnalyzeRequest, and the server always resolves it from
    the stored chunk instead.
    """
    session_id = "rereading-route-cannot-spoof"
    engagement_routes.session_state.start("u1", session_id)
    response = client.post(
        "/engagement/analyze",
        json={
            "frames": [{"landmarks": None} for _ in range(10)],
            "session_id": session_id,
            "content_id": CONTENT_ID,
            "chunk_id": "0",
            "chunk_order": 99,  # not a real field; must be silently ignored
            "dwell_seconds": 10.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["event"]["gaze_regression_detected"] is False

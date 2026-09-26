"""GET /engagement/calibration - whether a learner has calibrated.

Three properties matter and each is easy to break quietly:

  * it answers for the *caller* only - there is no parameter to ask about
    someone else
  * it never returns the calibration data itself, which is derived from the
    learner's face
  * it is authenticated

The answer decides which model a learner is served, so it is also worth pinning
that "no record" and "a record" really are the two outcomes.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.engagement import routes as engagement_routes
from app.main import app

client = TestClient(app)


class FakeCalibration:
    def __init__(self, records):
        self.records = records
        self.queries = []
        self.projections = []

    def find_one(self, query, projection=None):
        self.queries.append(query)
        self.projections.append(projection)
        for record in self.records:
            if all(record.get(k) == v for k, v in query.items()):
                return record
        return None


@pytest.fixture
def signed_in(monkeypatch):
    def _install(records, uid="u1"):
        fake = FakeCalibration(records)

        class DB:
            calibration = fake

        monkeypatch.setattr(engagement_routes, "db", DB())
        app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@t.com"}
        return fake

    yield _install
    app.dependency_overrides.clear()


def test_a_learner_with_no_record_is_not_calibrated(signed_in):
    signed_in(records=[])
    assert client.get("/engagement/calibration").json() == {"calibrated": False}


def test_a_learner_with_a_record_is_calibrated(signed_in):
    signed_in(records=[{"uid": "u1", "offset": [0.1] * 9, "pose_baseline": [1, 2, 3]}])
    assert client.get("/engagement/calibration").json() == {"calibrated": True}


def test_it_answers_for_the_caller_and_not_for_anyone_else(signed_in):
    # Someone else being calibrated must not make this learner look calibrated,
    # or they would be served a model trained on features they never had centred.
    fake = signed_in(records=[{"uid": "someone-else", "offset": [0.0] * 9}], uid="u1")
    assert client.get("/engagement/calibration").json() == {"calibrated": False}
    assert fake.queries == [{"uid": "u1"}]


def test_it_returns_a_boolean_and_nothing_derived_from_the_face(signed_in):
    signed_in(
        records=[
            {
                "uid": "u1",
                "offset": [0.123456] * 9,
                "pose_baseline": [9.87, 6.54, 3.21],
                "brow_baseline": 0.4242,
            }
        ]
    )
    body = client.get("/engagement/calibration").json()
    assert set(body) == {"calibrated"}
    assert "0.1234" not in str(body) and "9.87" not in str(body) and "0.4242" not in str(body)


def test_it_does_not_even_read_the_baselines_out_of_the_database(signed_in):
    # Defence in depth: the projection asks for the id only, so the biometric
    # fields are never loaded into the process for this endpoint at all.
    fake = signed_in(records=[{"uid": "u1", "offset": [0.0] * 9}])
    client.get("/engagement/calibration")
    assert fake.projections == [{"_id": 1}]


def test_it_needs_authentication():
    app.dependency_overrides.clear()
    assert client.get("/engagement/calibration").status_code == 401


def test_it_cannot_be_used_to_write(signed_in):
    signed_in(records=[])
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)("/engagement/calibration").status_code in (404, 405)

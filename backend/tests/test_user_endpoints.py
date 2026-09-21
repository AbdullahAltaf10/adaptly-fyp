"""
Endpoint-level tests for /users.

Uses an in-memory fake collection rather than MongoDB, so running the suite
never touches real Atlas data and needs no network.

Run from backend/:   python -m pytest tests/ -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.users import routes as user_routes  # noqa: E402
from app.auth import authorization  # noqa: E402


class FakeCollection:
    def __init__(self):
        self.docs = []

    def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None

    def find(self, query, projection=None):
        out = []
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                keep = {k: v for k, v in d.items() if k != "_id"}
                if projection:
                    wanted = {k for k, v in projection.items() if v == 1}
                    if wanted:
                        keep = {k: v for k, v in keep.items() if k in wanted}
                out.append(keep)
        return out

    def insert_one(self, doc):
        self.docs.append(dict(doc))

        class R:
            inserted_id = "fake-id"

        return R()

    def update_one(self, query, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))

                class R:
                    matched_count = 1

                return R()

        class R:
            matched_count = 0

        return R()


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(user_routes, "db", db)
    monkeypatch.setattr(authorization, "db", db)
    return db


def as_user(uid="u1", email="user@test.com"):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": email}


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


# ------------------------- registration -------------------------

def test_learner_can_register(fake_db):
    as_user()
    r = client.post("/users/register", params={"mode": "learner"})
    assert r.status_code == 200
    assert r.json()["mode"] == "learner"
    assert r.json()["role"] is None


def test_employee_can_register(fake_db):
    as_user()
    r = client.post("/users/register", params={"mode": "corporate", "role": "employee"})
    assert r.status_code == 200
    assert r.json()["role"] == "employee"


def test_self_registering_as_hr_admin_is_forbidden(fake_db, monkeypatch):
    """THE original defect: this used to succeed and grant admin access."""
    monkeypatch.delenv("HR_ADMIN_EMAILS", raising=False)
    as_user(email="attacker@evil.com")
    r = client.post("/users/register", params={"mode": "corporate", "role": "hr_admin"})
    assert r.status_code == 403
    assert fake_db.users.find_one({"uid": "u1"}) is None, "no profile should be created"


def test_learner_sending_hr_role_does_not_store_it(fake_db):
    as_user()
    r = client.post("/users/register", params={"mode": "learner", "role": "hr_admin"})
    assert r.status_code == 200
    assert fake_db.users.find_one({"uid": "u1"})["corporate_role"] is None


def test_invalid_mode_rejected(fake_db):
    as_user()
    r = client.post("/users/register", params={"mode": "superuser"})
    assert r.status_code == 400


def test_duplicate_registration_rejected(fake_db):
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    r = client.post("/users/register", params={"mode": "learner"})
    assert r.status_code == 400


# ------------------------- profile update -------------------------

def test_accessibility_settings_can_be_updated(fake_db):
    """Keys are the shared-contract ones: font, line_spacing, high_contrast, focus_isolation."""
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    r = client.put(
        "/users/me",
        json={"accessibility_settings": {"font": "opendyslexic", "line_spacing": 2.0}},
    )
    assert r.status_code == 200
    assert r.json()["accessibility_settings"] == {"font": "opendyslexic", "line_spacing": 2.0}


def test_study_preferences_can_be_updated(fake_db):
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    r = client.put("/users/me", json={"study_preferences": {"preferred_content_mode": "audio"}})
    assert r.status_code == 200
    assert r.json()["study_preferences"]["preferred_content_mode"] == "audio"


def test_profile_is_returned_in_contract_shape(fake_db):
    """user_id, not uid — the rename happens at the boundary, not in the database."""
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    body = client.get("/users/me").json()
    assert body["user_id"] == "u1"
    assert "uid" not in body
    assert body["schema_version"] == "1.0"
    assert body["mode"] == "learner"
    assert body["corporate_role"] is None, "must be present and null, not absent"


def test_cannot_escalate_role_through_profile_update(fake_db):
    """PUT /users/me must not be a back door to a privileged role."""
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    client.put(
        "/users/me",
        json={"accessibility_settings": {"font_size": "large"},
              "mode": "corporate", "corporate_role": "hr_admin"},
    )
    profile = fake_db.users.find_one({"uid": "u1"})
    assert profile["mode"] == "learner"
    assert profile["corporate_role"] is None


def test_unknown_settings_keys_are_stripped(fake_db):
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    r = client.put(
        "/users/me",
        json={"accessibility_settings": {"font": "opendyslexic", "is_admin": True}},
    )
    assert "is_admin" not in r.json()["accessibility_settings"]


# ------------------------- authorization -------------------------

def test_learner_cannot_reach_hr_directory(fake_db):
    as_user()
    client.post("/users/register", params={"mode": "learner"})
    assert client.get("/users/directory").status_code == 403


def test_employee_cannot_reach_hr_directory(fake_db):
    as_user()
    client.post("/users/register", params={"mode": "corporate", "role": "employee"})
    assert client.get("/users/directory").status_code == 403


def test_employee_cannot_promote_anyone(fake_db):
    as_user()
    client.post("/users/register", params={"mode": "corporate", "role": "employee"})
    r = client.put("/users/victim/corporate-role", json={"role": "hr_admin"})
    assert r.status_code == 403


def test_hr_admin_can_promote(fake_db, monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    as_user(uid="boss", email="boss@company.com")
    client.post("/users/register", params={"mode": "corporate", "role": "hr_admin"})

    fake_db.users.insert_one(
        {"uid": "emp1", "email": "e@c.com", "mode": "corporate", "corporate_role": "employee"}
    )
    r = client.put("/users/emp1/corporate-role", json={"role": "hr_admin"})
    assert r.status_code == 200
    assert fake_db.users.find_one({"uid": "emp1"})["corporate_role"] == "hr_admin"


def test_hr_admin_cannot_promote_a_learner(fake_db, monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    as_user(uid="boss", email="boss@company.com")
    client.post("/users/register", params={"mode": "corporate", "role": "hr_admin"})

    fake_db.users.insert_one(
        {"uid": "l1", "email": "l@c.com", "mode": "learner", "corporate_role": None}
    )
    assert client.put("/users/l1/corporate-role", json={"role": "hr_admin"}).status_code == 400


def test_promotion_rejects_invalid_role(fake_db, monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    as_user(uid="boss", email="boss@company.com")
    client.post("/users/register", params={"mode": "corporate", "role": "hr_admin"})
    fake_db.users.insert_one(
        {"uid": "e", "email": "e@c.com", "mode": "corporate", "corporate_role": "employee"}
    )
    assert client.put("/users/e/corporate-role", json={"role": "root"}).status_code == 400


def test_directory_returns_no_sensitive_fields(fake_db, monkeypatch):
    monkeypatch.setenv("HR_ADMIN_EMAILS", "boss@company.com")
    as_user(uid="boss", email="boss@company.com")
    client.post("/users/register", params={"mode": "corporate", "role": "hr_admin"})
    r = client.get("/users/directory")
    assert r.status_code == 200
    for row in r.json():
        assert set(row.keys()) <= {"uid", "email", "corporate_role"}

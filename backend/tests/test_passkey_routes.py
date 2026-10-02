"""
HTTP-level tests for /auth/passkeys/* — that routes.py wires the pydantic
request shapes and error mapping correctly. Crypto verification itself is
covered in tests/test_passkeys.py; here `verify_registration_response` /
`verify_authentication_response` are stubbed the same way.

Run from backend/:   python -m pytest tests/test_passkey_routes.py -v
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import passkeys, routes as auth_routes  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def fake_db(monkeypatch):
    database = mongomock.MongoClient().db
    monkeypatch.setattr(auth_routes, "db", database)
    database.users.insert_one({"uid": "u1", "email": "learner@test.com"})
    return database


def as_user(uid="u1", email="learner@test.com"):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": email}


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def register_a_passkey(monkeypatch, label="My laptop"):
    as_user()
    options_resp = client.post("/auth/passkeys/register/options")
    assert options_resp.status_code == 200
    challenge_id = options_resp.json()["challenge_id"]

    monkeypatch.setattr(
        passkeys, "verify_registration_response",
        lambda **kw: SimpleNamespace(credential_public_key=b"pk", sign_count=0),
    )
    verify_resp = client.post(
        "/auth/passkeys/register/verify",
        json={"challenge_id": challenge_id, "credential": {"id": "cred-abc"}, "label": label},
    )
    assert verify_resp.status_code == 200
    return challenge_id


def test_register_options_requires_auth(fake_db):
    r = client.post("/auth/passkeys/register/options")
    assert r.status_code == 401


def test_full_registration_round_trip(fake_db, monkeypatch):
    register_a_passkey(monkeypatch)

    listed = client.get("/auth/passkeys")
    assert listed.status_code == 200
    assert listed.json()[0]["credential_id"] == "cred-abc"
    assert listed.json()[0]["label"] == "My laptop"
    assert "public_key" not in listed.json()[0]


def test_revoking_a_passkey_removes_it(fake_db, monkeypatch):
    register_a_passkey(monkeypatch)
    r = client.delete("/auth/passkeys/cred-abc")
    assert r.status_code == 200
    assert client.get("/auth/passkeys").json() == []


def test_login_options_for_unknown_email_is_404(fake_db):
    r = client.post("/auth/passkeys/login/options", json={"email": "nobody@test.com"})
    assert r.status_code == 404


def test_login_options_for_account_without_a_passkey_is_404(fake_db):
    r = client.post("/auth/passkeys/login/options", json={"email": "learner@test.com"})
    assert r.status_code == 404


def test_full_signin_round_trip_returns_a_custom_token(fake_db, monkeypatch):
    register_a_passkey(monkeypatch)
    app.dependency_overrides.clear()  # sign-in must work with NO Firebase session

    options_resp = client.post("/auth/passkeys/login/options", json={"email": "learner@test.com"})
    assert options_resp.status_code == 200
    challenge_id = options_resp.json()["challenge_id"]

    monkeypatch.setattr(
        passkeys, "verify_authentication_response",
        lambda **kw: SimpleNamespace(new_sign_count=3),
    )
    monkeypatch.setattr(passkeys, "mint_custom_token", lambda uid: f"custom-token-{uid}")

    verify_resp = client.post(
        "/auth/passkeys/login/verify",
        json={"challenge_id": challenge_id, "credential": {"id": "cred-abc"}},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json() == {"custom_token": "custom-token-u1"}

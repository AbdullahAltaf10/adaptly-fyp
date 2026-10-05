"""
Tests for /auth/2fa/* and /auth/devices — device-trust email verification.

mongomock stands in for MongoDB (upsert, $inc and TTL-style expiry checks all
need real query semantics that the hand-rolled FakeCollection in
test_user_endpoints.py does not implement).

Run from backend/:   python -m pytest tests/test_twofactor.py -v
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import routes as auth_routes  # noqa: E402
from app.auth import twofactor  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def fake_db(monkeypatch):
    database = mongomock.MongoClient().db
    monkeypatch.setattr(auth_routes, "db", database)
    return database


@pytest.fixture
def sent_emails(monkeypatch):
    """Capture outgoing mail instead of touching a real SMTP server."""
    outbox = []

    def fake_send_email(to_address, subject, text_body):
        outbox.append({"to": to_address, "subject": subject, "body": text_body})

    monkeypatch.setattr(auth_routes, "send_email", fake_send_email)
    return outbox


def as_user(uid="u1", email="user@test.com"):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": email}


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def latest_code(outbox):
    """Codes are emailed as "...code is 123456...\\n\\n..." — pull the digits."""
    body = outbox[-1]["body"]
    return body.split("code is ")[1].split(".")[0]


# --------------------------------------------------------------- enabled flag

def test_enabled_is_false_without_gmail_credentials(monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    assert client.get("/auth/2fa/enabled").json() == {"enabled": False}


def test_enabled_is_true_with_gmail_credentials(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "bot@test.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x")
    assert client.get("/auth/2fa/enabled").json() == {"enabled": True}


# --------------------------------------------------------------- status

def test_new_device_is_not_trusted(fake_db):
    as_user()
    r = client.post("/auth/2fa/status", json={"device_id": "dev-1"})
    assert r.status_code == 200
    assert r.json() == {"trusted": False}


# --------------------------------------------------------------- send + verify

def test_send_emails_a_code_to_the_account_address(fake_db, sent_emails):
    as_user(email="learner@test.com")
    r = client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    assert r.status_code == 200
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "learner@test.com"


def test_correct_code_trusts_the_device(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    code = latest_code(sent_emails)

    r = client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": code})
    assert r.status_code == 200
    assert r.json() == {"trusted": True}

    status = client.post("/auth/2fa/status", json={"device_id": "dev-1"})
    assert status.json() == {"trusted": True}


def test_wrong_code_is_rejected_and_device_stays_untrusted(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})

    r = client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": "000000"})
    assert r.status_code == 400

    status = client.post("/auth/2fa/status", json={"device_id": "dev-1"})
    assert status.json() == {"trusted": False}


def test_five_wrong_attempts_locks_the_code_out(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    code = latest_code(sent_emails)

    for _ in range(twofactor.MAX_ATTEMPTS):
        client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": "000000"})

    # Even the RIGHT code no longer works once attempts are exhausted.
    r = client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": code})
    assert r.status_code == 400
    assert "Too many" in r.json()["detail"] or "new" in r.json()["detail"].lower()


def test_verifying_with_no_pending_code_is_rejected(fake_db):
    as_user()
    r = client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": "123456"})
    assert r.status_code == 400


def test_expired_code_is_rejected(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    code = latest_code(sent_emails)

    auth_routes.db.login_challenges.update_one(
        {"uid": "u1", "device_id": "dev-1"},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    r = client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": code})
    assert r.status_code == 400


def test_resending_too_soon_is_rate_limited(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    r = client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    assert r.status_code == 429
    assert len(sent_emails) == 1, "no second email should have gone out"


def test_trusting_one_device_does_not_trust_another(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    code = latest_code(sent_emails)
    client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": code})

    other = client.post("/auth/2fa/status", json={"device_id": "dev-2"})
    assert other.json() == {"trusted": False}


def test_trusting_a_device_does_not_trust_it_for_another_user(fake_db, sent_emails):
    as_user(uid="u1")
    client.post("/auth/2fa/send", json={"device_id": "shared-browser"})
    code = latest_code(sent_emails)
    client.post("/auth/2fa/verify", json={"device_id": "shared-browser", "code": code})

    as_user(uid="u2")
    status = client.post("/auth/2fa/status", json={"device_id": "shared-browser"})
    assert status.json() == {"trusted": False}


# --------------------------------------------------------------- device management

def test_trusted_devices_are_listed(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    code = latest_code(sent_emails)
    client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": code, "device_label": "Chrome on Windows"})

    r = client.get("/auth/devices")
    assert r.status_code == 200
    devices = r.json()
    assert len(devices) == 1
    assert devices[0]["device_id"] == "dev-1"
    assert devices[0]["label"] == "Chrome on Windows"


def test_revoking_a_device_removes_trust(fake_db, sent_emails):
    as_user()
    client.post("/auth/2fa/send", json={"device_id": "dev-1"})
    code = latest_code(sent_emails)
    client.post("/auth/2fa/verify", json={"device_id": "dev-1", "code": code})

    r = client.delete("/auth/devices/dev-1")
    assert r.status_code == 200

    status = client.post("/auth/2fa/status", json={"device_id": "dev-1"})
    assert status.json() == {"trusted": False}


def test_revoking_an_unknown_device_is_404(fake_db):
    as_user()
    r = client.delete("/auth/devices/never-trusted")
    assert r.status_code == 404

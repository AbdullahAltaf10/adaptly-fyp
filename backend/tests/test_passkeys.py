"""
Tests for app/auth/passkeys.py — the glue around the `webauthn` library.

These deliberately do NOT fabricate real WebAuthn attestation/assertion bytes;
producing a cryptographically valid one requires an actual authenticator (or
reimplementing COSE/CBOR signing by hand), and `webauthn` itself is already
tested upstream. What belongs to this codebase, and what these tests check,
is everything AROUND that call: challenge storage and expiry, that a
challenge cannot be replayed or used for the wrong account, and that a
successful verification is translated into the right Mongo writes and (for
sign-in) the right Firebase custom token.

Run from backend/:   python -m pytest tests/test_passkeys.py -v
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongomock  # noqa: E402
import pytest  # noqa: E402

from app.auth import passkeys  # noqa: E402
from app.auth.passkeys import PasskeyError  # noqa: E402
from webauthn.helpers.exceptions import (  # noqa: E402
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)


@pytest.fixture
def db():
    return mongomock.MongoClient().db


def register_profile(db, uid="u1", email="learner@test.com"):
    db.users.insert_one({"uid": uid, "email": email})


# --------------------------------------------------------------- registration

def test_registration_options_store_a_matching_challenge(db):
    register_profile(db)
    options, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")

    assert options["rp"]["id"] == "localhost"
    stored = db.passkey_challenges.find_one({"_id": challenge_id})
    assert stored["uid"] == "u1"
    assert stored["purpose"] == "register"


def test_registration_verify_stores_the_credential(db, monkeypatch):
    register_profile(db)
    _, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")

    fake_verification = SimpleNamespace(credential_public_key=b"public-key-bytes", sign_count=0)
    monkeypatch.setattr(passkeys, "verify_registration_response", lambda **kw: fake_verification)

    passkeys.verify_registration(db, "u1", challenge_id, {"id": "cred-abc"}, "My laptop")

    stored = db.passkey_credentials.find_one({"uid": "u1"})
    assert stored["credential_id"] == "cred-abc"
    assert stored["public_key"] == b"public-key-bytes"
    assert stored["label"] == "My laptop"

    # The challenge must not be reusable.
    assert db.passkey_challenges.find_one({"_id": challenge_id}) is None


def test_registration_verify_rejects_a_challenge_from_another_account(db, monkeypatch):
    register_profile(db, uid="u1")
    _, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")

    with pytest.raises(PasskeyError):
        passkeys.verify_registration(db, "u2", challenge_id, {"id": "cred-abc"}, None)


def test_registration_verify_rejects_an_expired_challenge(db, monkeypatch):
    register_profile(db)
    _, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")
    db.passkey_challenges.update_one(
        {"_id": challenge_id},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    with pytest.raises(PasskeyError):
        passkeys.verify_registration(db, "u1", challenge_id, {"id": "cred-abc"}, None)


def test_registration_verify_surfaces_library_rejection(db, monkeypatch):
    register_profile(db)
    _, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")

    def blow_up(**kw):
        raise InvalidRegistrationResponse("bad attestation")

    monkeypatch.setattr(passkeys, "verify_registration_response", blow_up)

    with pytest.raises(PasskeyError):
        passkeys.verify_registration(db, "u1", challenge_id, {"id": "cred-abc"}, None)


def test_list_passkeys_never_exposes_the_public_key(db, monkeypatch):
    register_profile(db)
    _, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")
    monkeypatch.setattr(
        passkeys, "verify_registration_response",
        lambda **kw: SimpleNamespace(credential_public_key=b"secret", sign_count=0),
    )
    passkeys.verify_registration(db, "u1", challenge_id, {"id": "cred-abc"}, "Phone")

    rows = passkeys.list_passkeys(db, "u1")
    assert len(rows) == 1
    assert "public_key" not in rows[0]


def test_revoke_passkey_only_removes_the_owners_copy(db, monkeypatch):
    register_profile(db, uid="u1")
    _, challenge_id = passkeys.build_registration_options(db, "u1", "learner@test.com")
    monkeypatch.setattr(
        passkeys, "verify_registration_response",
        lambda **kw: SimpleNamespace(credential_public_key=b"k", sign_count=0),
    )
    passkeys.verify_registration(db, "u1", challenge_id, {"id": "cred-abc"}, None)

    assert passkeys.revoke_passkey(db, "u2", "cred-abc") is False, "must not delete another user's passkey"
    assert passkeys.revoke_passkey(db, "u1", "cred-abc") is True


# --------------------------------------------------------------- authentication

def test_authentication_options_reject_unknown_email(db):
    with pytest.raises(PasskeyError, match="No account found"):
        passkeys.build_authentication_options(db, "nobody@test.com")


def test_authentication_options_reject_account_with_no_passkey(db):
    register_profile(db)
    with pytest.raises(PasskeyError, match="No passkey"):
        passkeys.build_authentication_options(db, "learner@test.com")


def _register_one_passkey(db, monkeypatch, uid="u1", credential_id="cred-abc"):
    register_profile(db, uid=uid)
    _, challenge_id = passkeys.build_registration_options(db, uid, "learner@test.com")
    monkeypatch.setattr(
        passkeys, "verify_registration_response",
        lambda **kw: SimpleNamespace(credential_public_key=b"pk", sign_count=0),
    )
    passkeys.verify_registration(db, uid, challenge_id, {"id": credential_id}, None)


def test_authentication_options_allow_the_registered_credential(db, monkeypatch):
    _register_one_passkey(db, monkeypatch)
    options, challenge_id = passkeys.build_authentication_options(db, "learner@test.com")

    allowed_ids = {c["id"] for c in options["allowCredentials"]}
    assert "cred-abc" in allowed_ids
    stored = db.passkey_challenges.find_one({"_id": challenge_id})
    assert stored["uid"] == "u1"
    assert stored["purpose"] == "login"


def test_authentication_verify_returns_a_custom_token(db, monkeypatch):
    _register_one_passkey(db, monkeypatch)
    _, challenge_id = passkeys.build_authentication_options(db, "learner@test.com")

    monkeypatch.setattr(
        passkeys, "verify_authentication_response",
        lambda **kw: SimpleNamespace(new_sign_count=7),
    )
    monkeypatch.setattr(passkeys, "mint_custom_token", lambda uid: f"token-for-{uid}")

    token = passkeys.verify_authentication(db, challenge_id, {"id": "cred-abc"})

    assert token == "token-for-u1"
    assert db.passkey_credentials.find_one({"credential_id": "cred-abc"})["sign_count"] == 7


def test_authentication_verify_rejects_an_unrecognised_credential(db, monkeypatch):
    _register_one_passkey(db, monkeypatch)
    _, challenge_id = passkeys.build_authentication_options(db, "learner@test.com")

    with pytest.raises(PasskeyError):
        passkeys.verify_authentication(db, challenge_id, {"id": "some-other-credential"})


def test_authentication_verify_rejects_a_replayed_challenge(db, monkeypatch):
    _register_one_passkey(db, monkeypatch)
    _, challenge_id = passkeys.build_authentication_options(db, "learner@test.com")
    monkeypatch.setattr(
        passkeys, "verify_authentication_response",
        lambda **kw: SimpleNamespace(new_sign_count=1),
    )
    monkeypatch.setattr(passkeys, "mint_custom_token", lambda uid: "token")

    passkeys.verify_authentication(db, challenge_id, {"id": "cred-abc"})

    with pytest.raises(PasskeyError):
        passkeys.verify_authentication(db, challenge_id, {"id": "cred-abc"})


def test_authentication_verify_surfaces_library_rejection(db, monkeypatch):
    _register_one_passkey(db, monkeypatch)
    _, challenge_id = passkeys.build_authentication_options(db, "learner@test.com")

    def blow_up(**kw):
        raise InvalidAuthenticationResponse("signature mismatch")

    monkeypatch.setattr(passkeys, "verify_authentication_response", blow_up)

    with pytest.raises(PasskeyError):
        passkeys.verify_authentication(db, challenge_id, {"id": "cred-abc"})

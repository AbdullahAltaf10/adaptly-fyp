"""
Passkey sign-in (WebAuthn), as a full alternative to email+password.

Two ceremonies, both standard WebAuthn:

- **Registration** happens to an already-signed-in learner (Firebase token
  present) adding a passkey from Settings. It proves the authenticator can
  produce signatures the server can verify later, and stores the public key.
- **Authentication** happens to a signed-OUT visitor, identified only by the
  email they type before the passkey prompt appears. There is no Firebase
  token yet — that is the whole point of passkey sign-in — so on success this
  module mints a Firebase *custom* token via `firebase.mint_custom_token`,
  which the frontend exchanges for a real session with
  `signInWithCustomToken`. That is the only bridge between WebAuthn (which
  Firebase does not speak) and the Firebase session every other route in the
  app expects.

A short-lived challenge document stands in for server-side session state
between "generate options" and "verify response", keyed by a random
`challenge_id` the frontend round-trips. Mongo enforces expiry is checked in
code, not by a TTL index, so tests do not depend on real wall-clock deletion.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, options_to_json_dict
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.auth.firebase import mint_custom_token

CHALLENGE_TTL_MINUTES = 5


class PasskeyError(Exception):
    """Raised with a message safe to show the learner."""


def _now() -> datetime:
    # Naive UTC - see the matching note in app/auth/twofactor.py: pymongo
    # hands back naive datetimes, so expires_at must be compared against one.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rp_config() -> tuple[str, str, str]:
    rp_id = os.getenv("WEBAUTHN_RP_ID", "localhost")
    rp_name = os.getenv("WEBAUTHN_RP_NAME", "Adaptly")
    # Vite's dev port can move (5173, 5174, ...) — see app/main.py's CORS note.
    # Passkeys are pinned to one exact origin by spec, so this must be the
    # single port actually in use, not a pattern.
    origin = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:5173")
    return rp_id, rp_name, origin


def _store_challenge(db, uid: str, challenge: bytes, purpose: str) -> str:
    challenge_id = uuid.uuid4().hex
    db.passkey_challenges.insert_one(
        {
            "_id": challenge_id,
            "uid": uid,
            "challenge": challenge,
            "purpose": purpose,
            "expires_at": _now() + timedelta(minutes=CHALLENGE_TTL_MINUTES),
        }
    )
    return challenge_id


def _consume_challenge(db, challenge_id: str, purpose: str) -> dict:
    doc = db.passkey_challenges.find_one({"_id": challenge_id})
    if not doc:
        raise PasskeyError("This passkey request has expired. Try again.")
    db.passkey_challenges.delete_one({"_id": challenge_id})
    if doc["purpose"] != purpose or _now() > doc["expires_at"]:
        raise PasskeyError("This passkey request has expired. Try again.")
    return doc


# ------------------------------------------------------------ registration

def build_registration_options(db, uid: str, email: str) -> tuple[dict, str]:
    rp_id, rp_name, _ = _rp_config()

    existing = list(db.passkey_credentials.find({"uid": uid}))
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"]))
        for row in existing
    ]

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=uid.encode("utf-8"),
        user_name=email,
        user_display_name=email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude or None,
    )
    challenge_id = _store_challenge(db, uid, options.challenge, "register")
    return options_to_json_dict(options), challenge_id


def verify_registration(db, uid: str, challenge_id: str, credential: dict, label: str | None) -> None:
    rp_id, _, origin = _rp_config()
    doc = _consume_challenge(db, challenge_id, "register")
    if doc["uid"] != uid:
        raise PasskeyError("This passkey request belongs to a different account.")

    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=doc["challenge"],
            expected_origin=origin,
            expected_rp_id=rp_id,
        )
    except InvalidRegistrationResponse as exc:
        raise PasskeyError("That passkey could not be registered.") from exc

    db.passkey_credentials.insert_one(
        {
            "uid": uid,
            "credential_id": credential["id"],
            "public_key": verification.credential_public_key,
            "sign_count": verification.sign_count,
            "label": label or "Passkey",
            "created_at": _now(),
        }
    )


def list_passkeys(db, uid: str) -> list[dict]:
    rows = db.passkey_credentials.find(
        {"uid": uid}, {"_id": 0, "public_key": 0}
    )
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def revoke_passkey(db, uid: str, credential_id: str) -> bool:
    result = db.passkey_credentials.delete_one({"uid": uid, "credential_id": credential_id})
    return result.deleted_count > 0


# ------------------------------------------------------------ authentication

def build_authentication_options(db, email: str) -> tuple[dict, str]:
    profile = db.users.find_one({"email": email})
    if not profile:
        raise PasskeyError("No account found for that email address.")

    credentials = list(db.passkey_credentials.find({"uid": profile["uid"]}))
    if not credentials:
        raise PasskeyError(
            "No passkey is set up for this account yet. Sign in with your "
            "password, then add a passkey from Settings."
        )

    rp_id, _, _ = _rp_config()
    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"]))
        for row in credentials
    ]
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_id = _store_challenge(db, profile["uid"], options.challenge, "login")
    return options_to_json_dict(options), challenge_id


def verify_authentication(db, challenge_id: str, credential: dict) -> str:
    """Returns a Firebase custom token on success."""
    rp_id, _, origin = _rp_config()
    doc = _consume_challenge(db, challenge_id, "login")
    uid = doc["uid"]

    row = db.passkey_credentials.find_one({"uid": uid, "credential_id": credential["id"]})
    if not row:
        raise PasskeyError("That passkey is not recognised.")

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=doc["challenge"],
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
        )
    except InvalidAuthenticationResponse as exc:
        raise PasskeyError("That passkey could not be verified.") from exc

    db.passkey_credentials.update_one(
        {"uid": uid, "credential_id": credential["id"]},
        {"$set": {"sign_count": verification.new_sign_count}},
    )
    return mint_custom_token(uid)

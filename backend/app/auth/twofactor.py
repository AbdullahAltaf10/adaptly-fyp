"""
Email-PIN device verification.

This is deliberately not "enter a code from an authenticator app" — the
learner base includes people for whom a second app is one more thing to lose
or forget. Instead: a 6-digit code lands in the same inbox Firebase already
uses, typed in once, and the *device* is remembered after that — not the
session, not the hour. A learner who signs back in tomorrow from the same
browser should not be challenged again. `device_id` is a random identifier
the frontend generates once and keeps in localStorage; it is not tied to any
hardware fingerprint, so clearing site data or using another browser is
indistinguishable from a new device, which is the correct, honest behaviour.

Codes are hashed before storage for the same reason passwords are: a database
read (backup, breach, curious teammate) must not hand over a live code.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

CODE_LENGTH = 6
CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 30


def _now() -> datetime:
    # Naive UTC on purpose: pymongo decodes BSON dates back as naive datetimes
    # (tz_aware=True is not set on this project's client), so a stored
    # expires_at compares only cleanly against another naive value. Mixing
    # aware and naive here raises TypeError, mongomock included - this bit
    # the tests before it would have bitten production.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def is_device_trusted(db, uid: str, device_id: str) -> bool:
    return db.trusted_devices.find_one({"uid": uid, "device_id": device_id}) is not None


def list_trusted_devices(db, uid: str) -> list[dict]:
    rows = db.trusted_devices.find({"uid": uid}, {"_id": 0})
    return sorted(rows, key=lambda r: r.get("last_seen_at") or r.get("created_at"), reverse=True)


def trust_device(db, uid: str, device_id: str, label: str | None) -> None:
    now = _now()
    db.trusted_devices.update_one(
        {"uid": uid, "device_id": device_id},
        {
            "$set": {"last_seen_at": now, "label": label or "Unlabelled device"},
            "$setOnInsert": {"uid": uid, "device_id": device_id, "created_at": now},
        },
        upsert=True,
    )


def revoke_device(db, uid: str, device_id: str) -> bool:
    result = db.trusted_devices.delete_one({"uid": uid, "device_id": device_id})
    return result.deleted_count > 0


class ResendTooSoon(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Resend available in {retry_after_seconds}s")


def start_challenge(db, uid: str, device_id: str) -> str:
    """
    Generate a fresh code, store its hash, and return the plaintext code for
    the caller to email. Raises ResendTooSoon if one was just sent for this
    uid/device pair.
    """
    existing = db.login_challenges.find_one({"uid": uid, "device_id": device_id})
    now = _now()
    if existing:
        age = (now - existing["created_at"]).total_seconds()
        if age < RESEND_COOLDOWN_SECONDS:
            raise ResendTooSoon(int(RESEND_COOLDOWN_SECONDS - age))

    code = generate_code()
    db.login_challenges.update_one(
        {"uid": uid, "device_id": device_id},
        {
            "$set": {
                "code_hash": hash_code(code),
                "expires_at": now + timedelta(minutes=CODE_TTL_MINUTES),
                "attempts": 0,
                "created_at": now,
            }
        },
        upsert=True,
    )
    return code


class ChallengeInvalid(Exception):
    """Raised with a message safe to show the learner."""


def verify_challenge(db, uid: str, device_id: str, code: str) -> None:
    """Raises ChallengeInvalid on any failure; returns normally on success."""
    challenge = db.login_challenges.find_one({"uid": uid, "device_id": device_id})
    if not challenge:
        raise ChallengeInvalid("No verification code is pending for this device. Request a new one.")

    if _now() > challenge["expires_at"]:
        db.login_challenges.delete_one({"uid": uid, "device_id": device_id})
        raise ChallengeInvalid("That code has expired. Request a new one.")

    if challenge.get("attempts", 0) >= MAX_ATTEMPTS:
        db.login_challenges.delete_one({"uid": uid, "device_id": device_id})
        raise ChallengeInvalid("Too many incorrect attempts. Request a new code.")

    if hash_code(code.strip()) != challenge["code_hash"]:
        db.login_challenges.update_one(
            {"uid": uid, "device_id": device_id}, {"$inc": {"attempts": 1}}
        )
        raise ChallengeInvalid("That code is incorrect.")

    db.login_challenges.delete_one({"uid": uid, "device_id": device_id})


def code_email_body(code: str) -> str:
    return (
        f"Your Adaptly verification code is {code}.\n\n"
        f"It expires in {CODE_TTL_MINUTES} minutes and can only be used once.\n\n"
        "If you did not try to sign in, you can ignore this email — your "
        "account is still safe."
    )

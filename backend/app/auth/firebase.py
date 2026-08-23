"""
Firebase Admin SDK — verifies the ID token the frontend sends on every request.

Initialisation is lazy for the same reasons as the database connection: the
prototype called `credentials.Certificate(...)` at import time, so importing the
application required the service-account file to be present. That made the test
suite depend on a real credential, and a missing file surfaced as a bare
`FileNotFoundError` with no explanation of what was expected or where.

The key file location can be overridden with FIREBASE_SERVICE_ACCOUNT, which is
useful for deployment where the credential is mounted elsewhere.
"""

import os

import firebase_admin
from firebase_admin import auth, credentials

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")

_initialised = False


def _service_account_path() -> str:
    return os.getenv("FIREBASE_SERVICE_ACCOUNT") or _DEFAULT_PATH


def _ensure_initialised():
    global _initialised
    if _initialised:
        return

    path = _service_account_path()
    if not os.path.exists(path):
        raise RuntimeError(
            f"Firebase service-account key not found at {path}. "
            "Download it from the Firebase console (Project settings > Service "
            "accounts > Generate new private key) and save it there, or set "
            "FIREBASE_SERVICE_ACCOUNT to its location. This file is a real "
            "credential and must never be committed."
        )

    # initialize_app raises if called twice, which happens under --reload.
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(path))
    _initialised = True


def verify_firebase_token(id_token: str):
    """Verify a Firebase ID token and return its decoded claims."""
    _ensure_initialised()
    return auth.verify_id_token(id_token)

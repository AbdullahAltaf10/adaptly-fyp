from typing import Optional

from fastapi import Header, HTTPException
from app.core.firebase import verify_firebase_token


def get_current_user(authorization: Optional[str] = Header(default=None)):
    # Header(default=None) rather than Header(...) on purpose: a required header
    # makes FastAPI reject a missing one with a 422 validation error before this
    # function runs, so an unauthenticated call looked like a malformed request.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split("Bearer ")[1]
    try:
        return verify_firebase_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

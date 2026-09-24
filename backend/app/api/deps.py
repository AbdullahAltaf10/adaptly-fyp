"""Shared FastAPI dependency for resolving the authenticated caller.

Wraps Module 1's real Firebase-based authentication
(``app.auth.dependencies.get_current_user``, merged into ``develop`` in #36)
and extracts the caller's uid. Every Module 8 endpoint resolves "who is the
logged-in learner" through this ONE dependency via FastAPI's ``Depends()``;
no endpoint ever accepts ``user_id`` as a client-supplied value (query
param, body field, etc.) — it always comes from here. See Issue #52.
"""

from __future__ import annotations

from fastapi import Depends

from app.auth.dependencies import get_current_user


def get_current_user_id(user: dict = Depends(get_current_user)) -> str:
    """Resolve the authenticated caller's user id from a verified Firebase token."""
    return user["uid"]

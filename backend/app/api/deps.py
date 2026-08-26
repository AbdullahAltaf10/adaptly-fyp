"""Shared FastAPI dependency for resolving the authenticated caller.

TEMPORARY — replace when Module 1 auth is merged (see Issue #34 for the real
integration). Real authentication (Module 1 — Learner Profile & Access
Management, Firebase-based per ``backend/README.md``) has not been merged
into ``develop`` yet. Rather than block Module 8's API work on that, or
hard-code something risky, every endpoint that needs "who is the logged-in
learner" resolves it through this ONE dependency via FastAPI's ``Depends()``.
Swapping in real Firebase-token verification later means changing only this
function's body — no endpoint code changes, and in particular no endpoint
ever accepts ``user_id`` as a client-supplied value (query param, body field,
etc.); it always comes from here.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

DEV_USER_HEADER = "X-Dev-User-Id"


def get_current_user_id(
    x_dev_user_id: str | None = Header(default=None, alias=DEV_USER_HEADER),
) -> str:
    """TEMPORARY placeholder auth — reads a dev-only header, not a real credential.

    This must never be mistaken for real authentication. It exists purely so
    the API layer has the right shape (one swappable dependency, never a
    trusted client-supplied user id) while Module 1's real auth is still
    unmerged.
    """

    if not x_dev_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                f"Missing '{DEV_USER_HEADER}' header. This is a temporary "
                "development placeholder for authentication, not real auth "
                "(see Issue #34 for the real integration)."
            ),
        )
    return x_dev_user_id

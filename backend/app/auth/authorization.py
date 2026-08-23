"""
Role-based authorization dependencies.

`get_current_user` proves WHO the caller is. It does not prove what they are
allowed to do. Until now the backend had no role check anywhere, so every
protection was enforced only by the frontend route guards — and a frontend
guard is trivially bypassed by calling the API directly with a valid token.

These dependencies close that gap. Use them on any endpoint that should be
restricted, for example:

    @router.get("/hr/completion-report")
    def report(user=Depends(require_hr_admin)):
        ...

They read the profile from MongoDB rather than trusting anything in the request,
so a caller cannot influence their own role by editing the payload.
"""

from fastapi import Depends, HTTPException

from app.core.db import db
from app.auth.dependencies import get_current_user
from app.auth.roles import MODE_CORPORATE, MODE_LEARNER, ROLE_HR_ADMIN


def get_current_profile(user=Depends(get_current_user)) -> dict:
    """The caller's stored profile. 404 if they authenticated but never registered."""
    profile = db.users.find_one({"uid": user["uid"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def require_mode(*allowed_modes: str):
    """Restrict an endpoint to one or more account modes."""

    def dependency(profile=Depends(get_current_profile)) -> dict:
        if profile.get("mode") not in allowed_modes:
            raise HTTPException(status_code=403, detail="Not permitted for this account type")
        return profile

    return dependency


def require_corporate_role(*allowed_roles: str):
    """
    Restrict an endpoint to specific corporate roles.

    Checks the mode as well as the role: a learner profile that somehow carried
    a stale corporate_role must not pass a role check.
    """

    def dependency(profile=Depends(get_current_profile)) -> dict:
        if profile.get("mode") != MODE_CORPORATE:
            raise HTTPException(status_code=403, detail="Not permitted for this account type")
        if profile.get("corporate_role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Not permitted for this role")
        return profile

    return dependency


# Convenience dependencies for the common cases.
require_learner = require_mode(MODE_LEARNER)
require_corporate = require_mode(MODE_CORPORATE)
require_hr_admin = require_corporate_role(ROLE_HR_ADMIN)

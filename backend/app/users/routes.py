from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth.authorization import require_hr_admin
from app.auth.dependencies import get_current_user
from app.auth.roles import (
    MODE_CORPORATE,
    VALID_CORPORATE_ROLES,
    resolve_registration_role,
)
from app.core.db import db
from app.users.contracts import to_contract
from app.users.models import build_user_doc

router = APIRouter(prefix="/users", tags=["users"])

# Strict allowlists. The profile-update endpoint previously accepted whatever
# object the client sent, which let a caller store arbitrary data on their own
# document. These names match the shared user-profile contract.
ALLOWED_ACCESSIBILITY_KEYS = {"font", "line_spacing", "high_contrast", "focus_isolation"}
ALLOWED_STUDY_PREFERENCE_KEYS = {
    "preferred_content_mode",
    "voice_responses_enabled",
    "preferred_voice_speed",
}


def _is_number(value) -> bool:
    # bool is a subclass of int in Python, so True would otherwise pass as 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# What each settings value must look like, straight from
# shared/contracts/user-profile.schema.json. The key allowlist above stops
# unknown fields; it said nothing about VALUES, so any client could store
# "font": "banana" or "line_spacing": "loose" - and did: the frontend saved
# names the contract has never had. A profile that breaks its own contract
# then breaks every consumer that trusts it, so the boundary refuses it.
_SETTING_RULES = {
    "font": (lambda v: v in ("default", "opendyslexic"), 'one of "default", "opendyslexic"'),
    "line_spacing": (lambda v: _is_number(v) and 1 <= v <= 3, "a number from 1 to 3"),
    "high_contrast": (lambda v: isinstance(v, bool), "true or false"),
    "focus_isolation": (lambda v: isinstance(v, bool), "true or false"),
    "preferred_content_mode": (lambda v: v in ("text", "audio", "mixed"), 'one of "text", "audio", "mixed"'),
    "voice_responses_enabled": (lambda v: isinstance(v, bool), "true or false"),
    "preferred_voice_speed": (lambda v: _is_number(v) and 0.5 <= v <= 2, "a number from 0.5 to 2"),
}


def _validate_setting_values(settings: dict) -> None:
    for key, value in settings.items():
        is_valid, expected = _SETTING_RULES[key]
        if not is_valid(value):
            raise HTTPException(status_code=400, detail=f"{key} must be {expected}")


@router.post("/register")
def register_profile(mode: str, role: str = None, user=Depends(get_current_user)):
    existing = db.users.find_one({"uid": user["uid"]})
    if existing:
        raise HTTPException(status_code=400, detail="Profile already exists")

    # The prototype took `mode` and `role` straight from the client with no
    # validation, so any authenticated user could register as hr_admin.
    # resolve_registration_role validates both and refuses to grant a
    # privileged role on request.
    try:
        resolved_mode, resolved_role = resolve_registration_role(
            mode, role, user.get("email")
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    doc = build_user_doc(user["uid"], user.get("email"), resolved_mode, resolved_role)
    db.users.insert_one(doc)
    return {"message": "Profile created", "mode": resolved_mode, "role": resolved_role}


@router.get("/me")
def get_profile(user=Depends(get_current_user)):
    """Own profile, in shared-contract shape."""
    profile = db.users.find_one({"uid": user["uid"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return to_contract(profile)


@router.put("/me")
def update_profile(payload: dict, user=Depends(get_current_user)):
    # Deliberately an allowlist. `mode` and `corporate_role` are NOT updatable
    # here - allowing them would reopen the privilege-escalation hole that
    # /register closes.
    updates = {}

    if "accessibility_settings" in payload:
        settings = payload["accessibility_settings"]
        if not isinstance(settings, dict):
            raise HTTPException(status_code=400, detail="accessibility_settings must be an object")
        cleaned = {k: v for k, v in settings.items() if k in ALLOWED_ACCESSIBILITY_KEYS}
        _validate_setting_values(cleaned)
        if cleaned:
            updates["accessibility_settings"] = cleaned

    if "study_preferences" in payload:
        prefs = payload["study_preferences"]
        if not isinstance(prefs, dict):
            raise HTTPException(status_code=400, detail="study_preferences must be an object")
        cleaned = {k: v for k, v in prefs.items() if k in ALLOWED_STUDY_PREFERENCE_KEYS}
        _validate_setting_values(cleaned)
        if cleaned:
            updates["study_preferences"] = cleaned

    if "display_name" in payload:
        name = payload["display_name"]
        if name is not None and (not isinstance(name, str) or len(name) > 100):
            raise HTTPException(status_code=400, detail="display_name must be a string up to 100 characters")
        updates["display_name"] = name

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Nothing to update. Allowed: accessibility_settings, study_preferences, display_name",
        )

    updates["updated_at"] = datetime.now(timezone.utc)

    result = db.users.update_one({"uid": user["uid"]}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = db.users.find_one({"uid": user["uid"]}, {"_id": 0})
    return to_contract(profile)


@router.put("/{target_uid}/corporate-role")
def set_corporate_role(target_uid: str, payload: dict, admin=Depends(require_hr_admin)):
    """
    Grant or change another user's corporate role. HR administrators only.

    Once the HR_ADMIN_EMAILS bootstrap has created the first administrator, this
    is the ONLY route to a privileged role - so escalation requires an existing
    administrator to act deliberately.
    """
    role = payload.get("role")
    if role not in VALID_CORPORATE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role must be one of: {', '.join(sorted(VALID_CORPORATE_ROLES))}",
        )

    target = db.users.find_one({"uid": target_uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("mode") != MODE_CORPORATE:
        raise HTTPException(
            status_code=400, detail="Only corporate accounts can hold a corporate role"
        )

    db.users.update_one(
        {"uid": target_uid},
        {"$set": {"corporate_role": role, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"message": "Role updated", "uid": target_uid, "corporate_role": role}


@router.get("/directory")
def list_corporate_users(admin=Depends(require_hr_admin)):
    """
    Minimal roster so an HR administrator can find the uid of someone to promote.

    Identifiers only. Never session content, engagement data or chat history -
    the scope document (section 6.1) states HR cannot access those.
    """
    users = db.users.find(
        {"mode": MODE_CORPORATE},
        {"_id": 0, "uid": 1, "email": 1, "corporate_role": 1},
    )
    return list(users)

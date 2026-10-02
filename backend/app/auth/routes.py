"""
/auth/* — device-trust 2FA and passkey sign-in.

Split from app/users/routes.py deliberately: those routes all assume a valid
Firebase token already exists. The passkey *login* endpoints here are the one
place in the whole API that must work for a caller who is not authenticated
yet — that is the entire mechanism, not an oversight.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import mailer, passkeys, twofactor
from app.auth.dependencies import get_current_user
from app.auth.mailer import MailerNotConfigured, send_email
from app.core.db import db

router = APIRouter(prefix="/auth", tags=["auth"])


# --------------------------------------------------------------- 2FA: schemas

class DeviceRequest(BaseModel):
    device_id: str


class VerifyCodeRequest(BaseModel):
    device_id: str
    code: str
    device_label: str | None = None


# --------------------------------------------------------------- 2FA: routes

@router.get("/2fa/enabled")
def two_factor_enabled():
    """
    No auth required — this only says whether the FEATURE can run at all, not
    anything about a specific account. RequireAuth reads it before deciding
    whether to gate navigation behind a code that Gmail is not configured to
    send.
    """
    return {"enabled": mailer.is_configured()}


@router.post("/2fa/status")
def two_factor_status(payload: DeviceRequest, user=Depends(get_current_user)):
    trusted = twofactor.is_device_trusted(db, user["uid"], payload.device_id)
    return {"trusted": trusted}


@router.post("/2fa/send")
def two_factor_send(payload: DeviceRequest, user=Depends(get_current_user)):
    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Account has no email address on file")

    try:
        code = twofactor.start_challenge(db, user["uid"], payload.device_id)
    except twofactor.ResendTooSoon as exc:
        raise HTTPException(
            status_code=429,
            detail=f"A code was just sent. Try again in {exc.retry_after_seconds}s.",
        ) from exc

    try:
        send_email(email, "Your Adaptly verification code", twofactor.code_email_body(code))
    except MailerNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"sent": True, "expires_in_minutes": twofactor.CODE_TTL_MINUTES}


@router.post("/2fa/verify")
def two_factor_verify(payload: VerifyCodeRequest, user=Depends(get_current_user)):
    try:
        twofactor.verify_challenge(db, user["uid"], payload.device_id, payload.code)
    except twofactor.ChallengeInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    twofactor.trust_device(db, user["uid"], payload.device_id, payload.device_label)
    return {"trusted": True}


@router.get("/devices")
def list_devices(user=Depends(get_current_user)):
    return twofactor.list_trusted_devices(db, user["uid"])


@router.delete("/devices/{device_id}")
def revoke_device(device_id: str, user=Depends(get_current_user)):
    removed = twofactor.revoke_device(db, user["uid"], device_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"revoked": True}


# ----------------------------------------------------------- passkeys: schemas

class PasskeyRegisterVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict
    label: str | None = None


class PasskeyLoginOptionsRequest(BaseModel):
    email: str


class PasskeyLoginVerifyRequest(BaseModel):
    challenge_id: str
    credential: dict


# ----------------------------------------------------------- passkeys: routes
# Registration — the caller already holds a Firebase session.

@router.post("/passkeys/register/options")
def passkey_register_options(user=Depends(get_current_user)):
    options, challenge_id = passkeys.build_registration_options(
        db, user["uid"], user.get("email") or user["uid"]
    )
    return {"options": options, "challenge_id": challenge_id}


@router.post("/passkeys/register/verify")
def passkey_register_verify(payload: PasskeyRegisterVerifyRequest, user=Depends(get_current_user)):
    try:
        passkeys.verify_registration(
            db, user["uid"], payload.challenge_id, payload.credential, payload.label
        )
    except passkeys.PasskeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"registered": True}


@router.get("/passkeys")
def passkey_list(user=Depends(get_current_user)):
    return passkeys.list_passkeys(db, user["uid"])


@router.delete("/passkeys/{credential_id}")
def passkey_revoke(credential_id: str, user=Depends(get_current_user)):
    removed = passkeys.revoke_passkey(db, user["uid"], credential_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Passkey not found")
    return {"revoked": True}


# Sign-in — deliberately NOT behind get_current_user. Proving identity via the
# passkey itself is the entire point; requiring a Firebase token first would
# defeat it.

@router.post("/passkeys/login/options")
def passkey_login_options(payload: PasskeyLoginOptionsRequest):
    try:
        options, challenge_id = passkeys.build_authentication_options(db, payload.email.strip())
    except passkeys.PasskeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"options": options, "challenge_id": challenge_id}


@router.post("/passkeys/login/verify")
def passkey_login_verify(payload: PasskeyLoginVerifyRequest):
    try:
        custom_token = passkeys.verify_authentication(db, payload.challenge_id, payload.credential)
    except passkeys.PasskeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"custom_token": custom_token}

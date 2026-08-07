from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user
from app.core.db import db
from app.models.user_model import build_user_doc

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/register")
def register_profile(mode: str, role: str = None, user=Depends(get_current_user)):
    existing = db.users.find_one({"uid": user["uid"]})
    if existing:
        raise HTTPException(status_code=400, detail="Profile already exists")
    doc = build_user_doc(user["uid"], user.get("email"), mode, role)
    db.users.insert_one(doc)
    return {"message": "Profile created", "mode": mode, "role": role}

@router.get("/me")
def get_profile(user=Depends(get_current_user)):
    profile = db.users.find_one({"uid": user["uid"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@router.put("/me")
def update_profile(payload: dict, user=Depends(get_current_user)):
    allowed_fields = {"accessibility_settings"}
    update_data = {k: v for k, v in payload.items() if k in allowed_fields}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    result = db.users.update_one({"uid": user["uid"]}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"message": "Profile updated"}
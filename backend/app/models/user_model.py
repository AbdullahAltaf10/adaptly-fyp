from datetime import datetime

def build_user_doc(uid: str, email: str, mode: str, role: str = None):
    return {
        "uid": uid,
        "email": email,
        "mode": mode,  # "learner" | "corporate"
        "corporate_role": role if mode == "corporate" else None,  # "employee" | "hr_admin"
        "accessibility_settings": {"font_size": "medium", "contrast": "normal"},
        "created_at": datetime.utcnow(),
    }
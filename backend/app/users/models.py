"""
The stored shape of a user profile.

This is the INTERNAL shape. It deliberately keeps the field names the working
implementation already uses (`uid` rather than `user_id`), because the team
agreed that the shared contracts define what modules SEND EACH OTHER, not how
each module stores its data. Conversion to the contract happens in contracts.py,
at the module boundary.
"""

from datetime import datetime, timezone

# Accessibility settings, matching shared/contracts/user-profile.schema.json.
#
# Note for anyone comparing this against the prototype: the prototype stored
# font_size / contrast / font_family. The shared contract uses font /
# line_spacing / high_contrast / focus_isolation, which is closer to what the
# scope document actually promises (section 4.1 lists OpenDyslexic font,
# adjustable line spacing, high contrast, and sentence-level focus isolation).
# line_spacing and focus_isolation were NOT implemented in the prototype - they
# are new here.
DEFAULT_ACCESSIBILITY = {
    "font": "default",          # "default" | "opendyslexic"
    "line_spacing": 1.5,        # 1.0 - 3.0
    "high_contrast": False,
    "focus_isolation": False,
}

DEFAULT_STUDY_PREFERENCES = {
    "preferred_content_mode": "text",   # "text" | "audio" | "mixed"
    "voice_responses_enabled": False,
    "preferred_voice_speed": 1.0,       # 0.5 - 2.0
}


def build_user_doc(uid: str, email: str, mode: str, role: str = None) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "schema_version": "1.0",
        "uid": uid,
        "email": email,
        "display_name": None,
        "mode": mode,                                          # "learner" | "corporate"
        "corporate_role": role if mode == "corporate" else None,
        "accessibility_settings": dict(DEFAULT_ACCESSIBILITY),
        "study_preferences": dict(DEFAULT_STUDY_PREFERENCES),
        "created_at": now,
        "updated_at": now,
    }

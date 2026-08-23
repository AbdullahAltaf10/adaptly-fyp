"""
Boundary conversion between the internal user document and the shared contract.

Why this file exists
--------------------
The team agreed that `shared/contracts/*.schema.json` define what modules SEND
EACH OTHER, not how each module stores data internally. That agreement is what
lets this module keep `uid` in MongoDB (26 existing queries, plus records
already written) instead of renaming the field everywhere for cosmetic reasons.

The cost of that agreement is exactly one function: convert here, at the point
where the data leaves this module. Nothing else in the codebase needs to know
the contract exists.

Anyone adding a field: change the internal shape in models.py, then map it here.
Do not rename internal fields to match the contract.
"""

from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"

# Every field the contract allows in accessibility_settings. Anything else is
# dropped rather than passed through, because the schema sets
# additionalProperties: false and would reject the whole object.
ACCESSIBILITY_FIELDS = ("font", "line_spacing", "high_contrast", "focus_isolation")
STUDY_PREFERENCE_FIELDS = (
    "preferred_content_mode",
    "voice_responses_enabled",
    "preferred_voice_speed",
)


def _iso(value) -> str:
    """Contract wants an ISO 8601 date-time string; Mongo gives us a datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value) if value is not None else datetime.now(timezone.utc).isoformat()


def to_contract(profile: dict) -> dict:
    """
    Convert a stored user document into user-profile.schema.json shape.

    Field renames applied here (internal -> contract):
        uid -> user_id

    `mode` and `corporate_role` need no renaming: the contract adopted the
    two-field structure this implementation already used, after review.
    """
    accessibility = profile.get("accessibility_settings") or {}
    preferences = profile.get("study_preferences") or {}

    contract = {
        "schema_version": SCHEMA_VERSION,
        "user_id": profile.get("uid"),
        "email": profile.get("email"),
        "display_name": profile.get("display_name"),
        "mode": profile.get("mode"),
        # The contract requires corporate_role to be PRESENT, and null for a
        # learner - not absent. .get() gives None, which serialises to null.
        "corporate_role": profile.get("corporate_role"),
        "accessibility_settings": {
            k: accessibility[k] for k in ACCESSIBILITY_FIELDS if k in accessibility
        },
        "created_at": _iso(profile.get("created_at")),
        "updated_at": _iso(profile.get("updated_at") or profile.get("created_at")),
    }

    # study_preferences is optional in the contract, so only include it when
    # there is something to say.
    prefs = {k: preferences[k] for k in STUDY_PREFERENCE_FIELDS if k in preferences}
    if prefs:
        contract["study_preferences"] = prefs

    return contract

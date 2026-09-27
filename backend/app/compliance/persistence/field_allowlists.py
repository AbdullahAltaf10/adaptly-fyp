"""Allowed storage fields for Module 10's compliance report collection,
mirrored from ``shared/contracts/compliance-report.schema.json`` -- the same
defense-in-depth pattern Module 8 uses in its own
``analytics/persistence/field_allowlists.py``: a write path filters every
document through this set before it reaches MongoDB, so nothing outside the
contract can ever be persisted, even by accident.
"""

from __future__ import annotations

COMPLIANCE_REPORT_FIELDS = {
    "schema_version",
    "score_version",
    "report_id",
    "session_id",
    "user_id",
    "content_id",
    "generated_at",
    "source_summary",
    "status",
    "engagement_quality_score",
    "components",
    "excluded_components",
    "critical_sections",
    "data_quality",
}


def filtered(document: dict, allowed_fields: set[str]) -> dict:
    """Return a copy of ``document`` containing only allow-listed keys."""

    return {key: value for key, value in document.items() if key in allowed_fields}

"""Module 10 compliance-report API endpoints (Issue #74).

Thin HTTP layer only, following Module 8's own
``analytics/api/routes.py`` conventions exactly: every endpoint resolves the
caller through ``get_current_user_id`` (never a client-supplied ``user_id``),
delegates generation to the Issue #74 service layer, and returns data
already shaped by the Issue #72/#73 contract. No score/evidence calculation
happens in this file.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.authorization import require_hr_admin
from app.auth.roles import MODE_CORPORATE, ROLE_HR_ADMIN
from app.core.db import db as users_db
from backend.app.api.deps import get_current_user_id
from backend.app.compliance.api.deps import get_repositories
from backend.app.compliance.service.generation import (
    ComplianceRepositories,
    GenerationResult,
    SessionAccessDeniedError,
    SessionNotFoundError,
    generate_report,
)

router = APIRouter(tags=["module-10-compliance"])


def _is_hr_admin(user_id: str) -> bool:
    """Soft HR-admin check: unlike ``require_hr_admin``, a caller with no
    registered profile at all is simply "not HR", not a 404 -- an owner
    fetching their own report must never be blocked just because they have
    no Module 1 profile row yet, mirroring how none of Module 8's own
    endpoints require one either.
    """

    profile = users_db.users.find_one({"uid": user_id}, {"_id": 0})
    if not profile:
        return False
    return profile.get("mode") == MODE_CORPORATE and profile.get("corporate_role") == ROLE_HR_ADMIN


@router.post("/api/sessions/{session_id}/compliance-report")
def post_generate_compliance_report(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    repositories: ComplianceRepositories = Depends(get_repositories),
) -> dict[str, Any]:
    try:
        result: GenerationResult = generate_report(session_id, user_id, repositories)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    except SessionAccessDeniedError:
        # Same non-leaking pattern as Module 8: a session that exists but
        # belongs to someone else looks identical to one that doesn't exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    if result.outcome == "no_summary":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason_code": "analytics_summary_missing", "message": result.reason},
        )

    return {
        "outcome": result.outcome,
        "report": result.report,
    }


@router.get("/api/sessions/{session_id}/compliance-report")
def get_compliance_report(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    repositories: ComplianceRepositories = Depends(get_repositories),
) -> dict[str, Any]:
    session = repositories.analytics.sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    is_owner = session["user_id"] == user_id
    if not is_owner and not _is_hr_admin(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    document = repositories.compliance_reports.get(session_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason_code": "compliance_report_missing",
                "message": "No compliance report has been generated for this session yet.",
            },
        )
    return document["report"]


@router.get("/api/compliance/reports")
def list_compliance_reports(
    admin: dict = Depends(require_hr_admin),
    repositories: ComplianceRepositories = Depends(get_repositories),
    user_id: str | None = Query(default=None),
    content_id: str | None = Query(default=None),
) -> dict[str, Any]:
    documents = repositories.compliance_reports.list(user_id=user_id, content_id=content_id)
    return {"items": [document["report"] for document in documents]}

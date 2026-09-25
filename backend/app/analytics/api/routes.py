"""Module 8 analytics and session-history API endpoints (Issue #29, #32).

Thin HTTP layer only: every endpoint resolves the caller through
``get_current_user_id`` (never a client-supplied ``user_id``), fetches data
through the Issue #27 repositories, and returns data already shaped by the
Issue #26/#28 contracts. No metric calculation and no MongoDB query building
happens in this file directly beyond simple ownership/state checks.

``POST .../insight-report/retry`` is the ONLY trigger for Gemini/fallback
generation (Issue #32, ``backend/app/analytics/insights``) anywhere in
Module 8 — ``GET .../analytics`` stays passive and only ever reads whatever
has already been generated and persisted; it never calls Gemini itself.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.analytics.api.deps import get_repositories
from backend.app.analytics.domain.metrics import DEFAULT_CONFIG, METRIC_VERSION
from backend.app.analytics.insights.gemini_client import call_gemini as _default_call_gemini
from backend.app.analytics.insights.generator import GeminiCaller, generate_insight_report
from backend.app.analytics.persistence.base import format_timestamp, utc_now
from backend.app.analytics.service.finalization import AnalyticsRepositories
from backend.app.api.deps import get_current_user_id

router = APIRouter(tags=["module-8-analytics"])


def get_gemini_caller() -> GeminiCaller:
    """FastAPI dependency for the Gemini call function.

    Overridden in tests (``app.dependency_overrides[get_gemini_caller] = ...``)
    with a fake callable, the same pattern used for ``get_repositories`` and
    ``get_current_user_id`` — no test ever performs a real network call to
    Gemini.
    """

    return _default_call_gemini


def _get_owned_session(
    repositories: AnalyticsRepositories, session_id: str, user_id: str
) -> dict[str, Any]:
    """Fetch a session, or raise 404 for both "missing" and "not yours".

    Using the same status/detail for both cases is deliberate: it avoids
    confirming to a caller that a session_id exists but belongs to someone
    else (an existence-leak the issue explicitly calls out).
    """

    session = repositories.sessions.get(session_id)
    if session is None or session["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found."
        )
    return session


def _require_completed_summary(
    repositories: AnalyticsRepositories, session: dict[str, Any]
) -> dict[str, Any]:
    """Fetch the persisted summary, or raise a clear, distinct 409.

    A session that exists but isn't finished yet, and a completed session
    whose summary is somehow missing, are different problems for a caller
    to react to, so they get distinct reason codes rather than one generic
    error.
    """

    if session["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason_code": "session_not_completed",
                "message": (
                    "This session has not finished yet. Post-session "
                    "analytics are only available after finalization."
                ),
            },
        )
    summary_document = repositories.session_analytics.get(
        session["session_id"], DEFAULT_CONFIG.metric_version
    )
    if summary_document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason_code": "analytics_summary_missing",
                "message": (
                    "This session is marked completed but no analytics "
                    "summary has been computed yet. Retry finalization."
                ),
            },
        )
    return summary_document


def _compact_summary(document: dict[str, Any]) -> dict[str, Any]:
    """Session-history list item: aggregates only, no raw timeline segments."""

    summary = document["summary"]
    compact = {key: value for key, value in summary.items() if key != "timeline_segments"}
    compact["insight_report_status"] = document["insight_report_status"]
    return compact


def _placeholder_learning_profile(user_id: str) -> dict[str, Any]:
    """Contract-shaped placeholder until Issue #33 computes the real thing.

    Matches ``learning-profile.schema.json`` exactly so nothing about this
    endpoint's response shape needs to change once #33 lands — only the
    values will stop being placeholders.
    """

    return {
        "schema_version": "1.0",
        "metric_version": METRIC_VERSION,
        "user_id": user_id,
        "sessions_analyzed": 0,
        "analysis_date_range": {"started_at": None, "ended_at": None},
        "average_session_duration_seconds": None,
        "average_focus_percentage": None,
        "focus_trend": "insufficient_data",
        "recovery_trend": "insufficient_data",
        "intervention_effectiveness_by_type": [],
        "assistant_usage_patterns": {
            "sessions_with_assistant_use": 0,
            "average_learner_messages_per_session": None,
            "typed_input_count": 0,
            "voice_input_count": 0,
            "suggested_question_count": 0,
            "preferred_input_mode": "unknown",
        },
        "recurring_difficulty_areas": [],
        "effective_support_methods": [],
        "critical_section_aggregates": {
            "sections_observed": 0,
            "sessions_with_critical_sections": 0,
            "average_engagement_rate": None,
            "average_focus_percentage": None,
        },
        "data_quality": {
            "sessions_with_sufficient_data": 0,
            "average_event_coverage_rate": None,
            "flags": ["insufficient_sessions"],
        },
        "computed_at": format_timestamp(utc_now()),
    }


@router.get("/api/sessions/{session_id}/analytics")
def get_session_analytics(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    repositories: AnalyticsRepositories = Depends(get_repositories),
) -> dict[str, Any]:
    session = _get_owned_session(repositories, session_id, user_id)
    summary_document = _require_completed_summary(repositories, session)

    report = repositories.insight_reports.get(session_id)
    response = dict(summary_document["summary"])
    response["insight_report"] = {
        "status": summary_document["insight_report_status"],
        "report_text": report["report_text"] if report else None,
    }
    return response


@router.get("/api/analytics/sessions")
def get_session_history(
    user_id: str = Depends(get_current_user_id),
    repositories: AnalyticsRepositories = Depends(get_repositories),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    content_id: str | None = Query(default=None),
) -> dict[str, Any]:
    items, total_count = repositories.session_analytics.list_by_user_page(
        user_id, limit=limit, offset=offset, content_id=content_id
    )
    return {
        "items": [_compact_summary(document) for document in items],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "returned_count": len(items),
            "total_count": total_count,
        },
    }


@router.get("/api/analytics/learning-profile")
def get_learning_profile(
    user_id: str = Depends(get_current_user_id),
    repositories: AnalyticsRepositories = Depends(get_repositories),
) -> dict[str, Any]:
    profile = repositories.learning_profiles.get(user_id)
    if profile is not None:
        return profile
    return _placeholder_learning_profile(user_id)


@router.post("/api/sessions/{session_id}/insight-report/retry")
def retry_insight_report(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    repositories: AnalyticsRepositories = Depends(get_repositories),
    call_gemini: GeminiCaller = Depends(get_gemini_caller),
) -> dict[str, Any]:
    """Generate (first attempt) or retry (after "failed") the insight report.

    This is the ONLY place in Module 8 that ever calls Gemini or the
    deterministic fallback. Never recomputes or re-saves the numeric session
    summary — only the separate insight-report document and the summary's
    ``insight_report_status`` envelope field are touched. A report that
    already reached ``"generated"`` or ``"fallback_generated"`` is left
    untouched and reported back as-is, matching the once-per-status-
    transition contract (free-tier Gemini quota is not re-spent on a report
    that already exists).
    """

    session = _get_owned_session(repositories, session_id, user_id)
    summary_document = _require_completed_summary(repositories, session)
    current_status = summary_document["insight_report_status"]

    if current_status in ("generated", "fallback_generated"):
        return {
            "session_id": session_id,
            "insight_report_status": current_status,
            "retried": False,
            "message": "An insight report already exists for this session; nothing to retry.",
        }

    existing_report = repositories.insight_reports.get(session_id)
    retry_count = existing_report["retry_count"] + 1 if existing_report else 0

    report = generate_insight_report(
        summary_document["summary"],
        session_id=session_id,
        user_id=user_id,
        call_gemini=call_gemini,
        retry_count=retry_count,
    )
    repositories.insight_reports.save(report)
    repositories.session_analytics.set_insight_report_status(
        session_id, summary_document["summary"]["metric_version"], report["status"]
    )

    if report["status"] == "generated":
        message = "A written summary was generated for this session."
    elif report["status"] == "fallback_generated":
        message = (
            "Gemini was unavailable, so a summary was generated from your "
            "session numbers instead."
        )
    else:
        message = "The written summary could not be generated. You can try again."

    return {
        "session_id": session_id,
        "insight_report_status": report["status"],
        "retried": True,
        "message": message,
    }

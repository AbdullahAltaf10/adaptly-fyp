"""Orchestrates Module 8's insight-report generation (Issue #32).

Tries Gemini first; ANY failure at all — missing API key, missing package,
network/timeout error, or a response that fails validation — falls back to
the deterministic report. Pure with respect to infrastructure: takes an
already-computed session summary and an injected ``call_gemini`` callable,
and returns a plain dict shaped like
``shared/contracts/analytics-report.schema.json``. Never touches MongoDB or
FastAPI directly — those live in
``backend/app/analytics/persistence/insight_reports.py`` and
``backend/app/analytics/api/routes.py`` respectively, which is what makes
``call_gemini`` injectable/mockable for tests without any network access.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.app.analytics.insights.fallback import build_fallback_report
from backend.app.analytics.insights.gemini_client import load_gemini_config
from backend.app.analytics.insights.prompt import build_prompt
from backend.app.analytics.insights.validation import validate_report_text
from backend.app.analytics.persistence.base import format_timestamp, utc_now

SCHEMA_VERSION = "1.0"

GeminiCaller = Callable[[str], str]


def generate_insight_report(
    summary: dict[str, Any],
    *,
    session_id: str,
    user_id: str,
    call_gemini: GeminiCaller,
    retry_count: int = 0,
    now: Any = None,
) -> dict[str, Any]:
    """Generate (first attempt) or regenerate (a retry) one session's report.

    ``retry_count`` is supplied by the caller (the API layer knows whether
    this is the very first attempt, or an actual retry the
    ``/insight-report/retry`` route decided to allow — see that route's
    ``error_code``/``retry_count`` bound) so this function stays a pure
    calculation with no persistence lookups of its own. The only way this
    returns ``status: "failed"`` is if building the deterministic fallback
    itself raises — which should never happen for a contract-valid summary,
    but is handled explicitly rather than left to crash the retry endpoint.
    """

    now_str = format_timestamp(now or utc_now())
    report_id = f"insight-{session_id}"
    base = {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "session_id": session_id,
        "user_id": user_id,
        "retry_count": retry_count,
        "last_attempted_at": now_str,
    }

    config = load_gemini_config()
    error_code: str | None = None
    try:
        prompt = build_prompt(summary)
        raw_text = call_gemini(prompt)
        report_text = validate_report_text(raw_text)
        return {
            **base,
            "status": "generated",
            "report_text": report_text,
            "generation_method": "gemini",
            "model_name": config.model_name,
            "model_version": None,
            "generated_at": now_str,
            "fallback_used": False,
            "error_code": None,
        }
    except Exception as error:  # noqa: BLE001 - deliberately catch-all: any
        # Gemini/validation failure at all must fall back, never propagate.
        error_code = type(error).__name__

    try:
        fallback_text = build_fallback_report(summary)
    except Exception as fallback_error:  # noqa: BLE001 - see module docstring
        return {
            **base,
            "status": "failed",
            "report_text": None,
            "generation_method": "none",
            "model_name": None,
            "model_version": None,
            "generated_at": None,
            "fallback_used": False,
            "error_code": type(fallback_error).__name__,
        }

    return {
        **base,
        "status": "fallback_generated",
        "report_text": fallback_text,
        "generation_method": "deterministic_fallback",
        "model_name": None,
        "model_version": None,
        "generated_at": now_str,
        "fallback_used": True,
        "error_code": error_code,
    }

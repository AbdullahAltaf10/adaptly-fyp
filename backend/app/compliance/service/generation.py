"""Module 10 compliance-report generation orchestration (Issue #74).

Connects the pure report builder (Issue #73,
``backend/app/compliance/domain/report.py``) with persistence -- this
module owns generation *lifecycle* decisions (does the caller own this
session? does a finalized Module 8 summary exist yet? has a report already
been generated?) and does not calculate any score or evidence itself.

Reuses Module 8's own ``AnalyticsRepositories`` bundle to read the session,
its finalized summary, its chunk-progress records, and its raw intervention
events -- the same repositories Module 8's own ``finalize_session`` already
reads from, imported here rather than duplicated. This is read-only reuse:
nothing in this module writes to any Module 8 collection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.app.analytics.domain.metrics import DEFAULT_CONFIG as METRIC_DEFAULT_CONFIG
from backend.app.analytics.service.finalization import AnalyticsRepositories
from backend.app.compliance.domain.report import build_compliance_report
from backend.app.compliance.domain.score import DEFAULT_CONFIG as SCORE_DEFAULT_CONFIG
from backend.app.compliance.domain.score import ScoreConfig
from backend.app.compliance.persistence.base import format_timestamp, utc_now
from backend.app.compliance.persistence.reports import ComplianceReportRepository

Outcome = Literal["generated", "already_exists", "rejected", "no_summary"]


class SessionNotFoundError(Exception):
    """Raised when the requested session_id does not exist."""


class SessionAccessDeniedError(Exception):
    """Raised when the requesting user does not own the session."""


@dataclass(frozen=True)
class GenerationResult:
    outcome: Outcome
    report: dict[str, Any] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ComplianceRepositories:
    """Bundles what Issue #74 needs: Module 8's analytics repositories
    (read-only reuse) plus Module 10's own compliance-report repository."""

    analytics: AnalyticsRepositories
    compliance_reports: ComplianceReportRepository

    @classmethod
    def from_database(cls, analytics_database: Any, compliance_database: Any) -> "ComplianceRepositories":
        return cls(
            analytics=AnalyticsRepositories.from_database(analytics_database),
            compliance_reports=ComplianceReportRepository(compliance_database),
        )


def _build_chunk_context(chunk_progress_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirrors ``finalization.py``'s own adapter exactly -- Module 10 reads
    the same stored chunk-progress rows Module 8's finalization already
    reads, so both modules see one consistent notion of ``is_critical``.
    """

    return [
        {
            "chunk_id": record.get("chunk_id"),
            "is_critical": bool(record.get("is_critical")),
            "completed": record.get("status") == "completed"
            or record.get("completed_at") is not None,
        }
        for record in chunk_progress_records
    ]


def generate_report(
    session_id: str,
    requesting_user_id: str,
    repositories: ComplianceRepositories,
    *,
    now: Any = None,
    score_config: ScoreConfig = SCORE_DEFAULT_CONFIG,
) -> GenerationResult:
    """Generate (or return the existing) compliance report for one session.

    Idempotent: an existing report is returned unchanged, never
    recalculated -- an attestation is a record of what was observed, not a
    live-recomputed figure (see the Issue #74 doc for why).
    """

    session = repositories.analytics.sessions.get(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    if session["user_id"] != requesting_user_id:
        raise SessionAccessDeniedError(session_id)

    existing = repositories.compliance_reports.get(session_id)
    if existing is not None:
        return GenerationResult(outcome="already_exists", report=existing["report"])

    if session["status"] != "completed":
        return GenerationResult(
            outcome="no_summary",
            reason=(
                "This session has not finished yet. A compliance report can "
                "only be generated once Module 8 has finalized the session."
            ),
        )

    summary_document = repositories.analytics.session_analytics.get(
        session_id, METRIC_DEFAULT_CONFIG.metric_version
    )
    if summary_document is None:
        return GenerationResult(
            outcome="no_summary",
            reason=(
                "This session is marked completed but no analytics summary "
                "has been computed yet. Retry once Module 8's finalization "
                "has produced one."
            ),
        )

    chunk_context = _build_chunk_context(
        repositories.analytics.chunk_progress.list_by_session(session_id)
    )
    intervention_events = repositories.analytics.intervention_events.list_by_session(
        session_id
    )

    now_str = format_timestamp(now or utc_now())
    report = build_compliance_report(
        summary_document["summary"],
        report_id=f"report-{session_id}",
        generated_at=now_str,
        chunk_context=chunk_context,
        intervention_events=intervention_events,
        config=score_config,
    )

    repositories.compliance_reports.save(report, now=now_str)

    return GenerationResult(outcome="generated", report=report)

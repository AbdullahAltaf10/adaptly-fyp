"""Module 8 session finalization (Issue #28).

Orchestration layer that connects the pure metric engine (Issue #26,
``backend/app/analytics/domain/metrics.py``) with the persistence layer
(Issue #27, ``backend/app/analytics/persistence``). This module owns session
*lifecycle* decisions (is this session eligible to finish? does it belong to
this learner? what is its final duration?) — it does not calculate analytics
itself, and it does not know anything about MongoDB internals beyond calling
repository methods.

Deliberately excluded: any Gemini/LLM import. Insight-report generation
(Issue #32) is a separate downstream step; ``SessionAnalyticsRepository.save``
already records ``insight_report_status="pending"`` so that step has
something to pick up later. Numeric finalization must succeed independent of
whether an insight report is ever generated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from backend.app.analytics.domain.metrics import (
    DEFAULT_CONFIG,
    MetricConfig,
    build_session_summary,
)
from backend.app.analytics.persistence.base import format_timestamp, utc_now
from backend.app.analytics.persistence.events import (
    AssistantEventRepository,
    EngagementEventRepository,
    InterventionEventRepository,
)
from backend.app.analytics.persistence.learning_profiles import (
    LearningProfileRepository,
)
from backend.app.analytics.persistence.session_analytics import (
    SessionAnalyticsRepository,
)
from backend.app.analytics.persistence.sessions import (
    ChunkProgressRepository,
    SessionRepository,
)

ELIGIBLE_STATUSES = ("active", "paused")
Outcome = Literal["finalized", "already_finalized", "rejected", "failed"]


class SessionNotFoundError(Exception):
    """Raised when the requested session_id does not exist."""


class SessionAccessDeniedError(Exception):
    """Raised when the requesting user does not own the session."""


@dataclass(frozen=True)
class FinalizationResult:
    outcome: Outcome
    session: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    reason_code: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AnalyticsRepositories:
    """Bundles the Issue #27 repositories finalization depends on."""

    sessions: SessionRepository
    engagement_events: EngagementEventRepository
    intervention_events: InterventionEventRepository
    assistant_events: AssistantEventRepository
    chunk_progress: ChunkProgressRepository
    session_analytics: SessionAnalyticsRepository
    learning_profiles: LearningProfileRepository

    @classmethod
    def from_database(cls, database: Any) -> "AnalyticsRepositories":
        return cls(
            sessions=SessionRepository(database),
            engagement_events=EngagementEventRepository(database),
            intervention_events=InterventionEventRepository(database),
            assistant_events=AssistantEventRepository(database),
            chunk_progress=ChunkProgressRepository(database),
            session_analytics=SessionAnalyticsRepository(database),
            learning_profiles=LearningProfileRepository(database),
        )


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Return a timezone-aware UTC datetime, or None if unparseable/missing.

    Mirrors the domain layer's own timestamp strictness (timezone-aware
    ISO 8601 required) but stays local to this module rather than reaching
    into ``domain.metrics`` private helpers, keeping the two layers
    independently readable.
    """

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _build_chunk_context(
    chunk_progress_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Adapt stored chunk-progress rows into the shape the metric engine
    expects (``{"chunk_id", "is_critical", "completed"}``).

    A record with no ``is_critical`` recorded is treated as not critical,
    mirroring the same default already established for content chunks in
    ``content.schema.json`` (``is_critical`` defaults to ``false``) — this is
    not a new assumption, just the existing contract default carried through.
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


def finalize_session(
    session_id: str,
    requesting_user_id: str,
    repositories: AnalyticsRepositories,
    *,
    now: datetime | str | None = None,
    config: MetricConfig = DEFAULT_CONFIG,
) -> FinalizationResult:
    """Finalize a session: verify, close out timing, compute and store the
    Module 8 summary, and mark the session completed.

    Idempotent: re-finalizing an already-completed session with an existing
    summary returns that summary unchanged rather than recomputing or
    duplicating it. Failure-safe: nothing is written to the session or the
    summary collection unless analytics computation succeeds.
    """

    session = repositories.sessions.get(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)
    if session["user_id"] != requesting_user_id:
        raise SessionAccessDeniedError(session_id)

    status = session["status"]

    if status == "completed":
        existing = repositories.session_analytics.get(
            session_id, config.metric_version
        )
        if existing is not None:
            return FinalizationResult(
                outcome="already_finalized",
                session=session,
                summary=existing["summary"],
            )
        # Session was marked completed but its summary is missing (e.g. a
        # prior finalization attempt died after the session write but before
        # the summary write). Self-heal by recomputing from the session's
        # already-authoritative timing, without touching session state again.
        finalized_session = session
    elif status in ELIGIBLE_STATUSES:
        started_at = _parse_iso_datetime(session.get("started_at"))
        if started_at is None:
            return FinalizationResult(
                outcome="failed",
                session=session,
                reason_code="invalid_start_time",
                reason=(
                    "started_at is missing or not a timezone-aware ISO 8601 "
                    "timestamp; cannot calculate duration."
                ),
            )
        ended_at = _parse_iso_datetime(now) if now is not None else utc_now()
        if ended_at is None:
            ended_at = utc_now()
        if ended_at < started_at:
            return FinalizationResult(
                outcome="failed",
                session=session,
                reason_code="invalid_timestamp_order",
                reason="Session end time precedes its start time.",
            )
        # No pause-interval field exists in the session contract (documented,
        # intentionally-unresolved gap — see CLAUDE.md 6.6 / the session
        # schema). Wall-clock start-to-end is therefore the authoritative
        # duration, and any paused time is included in it. This is a known
        # limitation, not something to silently invent a fix for here.
        duration_seconds = round((ended_at - started_at).total_seconds())
        finalized_session = dict(session)
        finalized_session["status"] = "completed"
        finalized_session["ended_at"] = format_timestamp(ended_at)
        finalized_session["duration_seconds"] = duration_seconds
    elif status == "abandoned":
        return FinalizationResult(
            outcome="rejected",
            session=session,
            reason_code="session_abandoned",
            reason="Abandoned sessions are not eligible for standard finalization.",
        )
    else:
        return FinalizationResult(
            outcome="rejected",
            session=session,
            reason_code="session_not_eligible",
            reason=f"Session status '{status}' is not eligible for finalization.",
        )

    engagement_events = repositories.engagement_events.list_by_session(session_id)
    intervention_events = repositories.intervention_events.list_by_session(session_id)
    assistant_events = repositories.assistant_events.list_by_session(session_id)
    chunk_context = _build_chunk_context(
        repositories.chunk_progress.list_by_session(session_id)
    )

    try:
        summary = build_session_summary(
            finalized_session,
            engagement_events,
            intervention_events,
            assistant_events,
            computed_at=finalized_session.get("ended_at") or utc_now(),
            chunk_context=chunk_context,
            config=config,
        )
    except (ValueError, TypeError, KeyError) as error:
        # Nothing has been written yet: the session record on disk is still
        # in its pre-finalization state, so a corrected retry can simply
        # call finalize_session again.
        return FinalizationResult(
            outcome="failed",
            session=session,
            reason_code="analytics_computation_failed",
            reason=str(error),
        )

    if status in ELIGIBLE_STATUSES:
        repositories.sessions.upsert_session(
            finalized_session, now=finalized_session["ended_at"]
        )
    repositories.session_analytics.save(
        summary,
        insight_report_status="pending",
        now=finalized_session.get("ended_at"),
    )

    return FinalizationResult(
        outcome="finalized", session=finalized_session, summary=summary
    )

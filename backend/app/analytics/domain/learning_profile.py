"""Deterministic, infrastructure-independent Module 8 learning-profile
calculations (Issue #33).

Mirrors the layering ``metrics.py`` (Issue #26) already established: this
module accepts ordinary mappings/sequences and returns a plain dict shaped
like ``shared/contracts/learning-profile.schema.json``. It deliberately does
not import MongoDB, FastAPI, or anything from ``backend/app/analytics/
persistence`` or ``backend/app/analytics/api`` — wiring this into a real
repository/endpoint is explicitly out of scope for this issue, the same way
building the metric engine (#26) didn't touch persistence (#27) or the API
(#29).

The only input this module ever sees is a list of already-computed,
contract-shaped session summaries (``session-summary.schema.json``) — never
raw engagement/intervention/assistant events, and never anything
webcam-derived. There is no code path here by which raw biometric data could
reach a learning profile even by accident, since summaries are the only
thing this module's public function accepts.

Design decisions worth knowing before reading the code:

1. **Contract vs. issue prose.** Issue #33's prose mentions a "longest-focus
   trend" and an "average recovery-duration trend" as if they were separate
   fields. ``learning-profile.schema.json`` (``additionalProperties: false``)
   has no such fields — only one ``focus_trend`` and one ``recovery_trend``
   enum. Per CLAUDE.md 6.3 ("existing contracts are authoritative"), this
   module computes exactly what the schema defines and does not invent new
   fields to match the issue's informal field list.

2. **The effective-support-methods evidence threshold (CLAUDE.md 6.6, gap
   #4)** was explicitly left undefined pending a decision made "via
   config/metric-version/tests, not invented silently." Decided here as
   ``LearningProfileConfig.minimum_evidence_count_for_effective_support``
   (default 3 evaluable outcomes) and ``effective_support_min_rate``
   (default 0.6) — a support type is only ever listed as "effective" once
   both are met. Below the evidence count, the type simply doesn't appear in
   ``effective_support_methods`` (it can still appear in
   ``intervention_effectiveness_by_type``, which has no such gate).

3. **Small-sample caution (CLAUDE.md 6.5, rule #7)** governs every trend
   field: with fewer than ``minimum_sessions_for_trend`` qualifying data
   points, the trend is ``"insufficient_data"`` rather than a guess.

4. **``critical_section_aggregates.average_focus_percentage``** has no
   directly corresponding per-session field — session summaries record
   critical-section *focused seconds* and an *engagement rate*, not a
   critical-section-scoped focus percentage. Rather than fabricate a
   denominator that doesn't exist in the data, this is computed as the
   average of each session's overall ``engagement_distribution.focused.
   percentage``, restricted to sessions that had at least one critical
   section — a defensible, data-grounded reading of an underspecified field,
   documented here rather than invented silently.

5. **``recurring_difficulty_areas``** is derived from repeated
   ``struggling``/``fatigued`` timeline segments tied to the same
   ``(content_id, chunk_id)`` pair across multiple sessions — not from
   intervention records, since an intervention's own
   ``triggering_engagement_state`` already correlates with the same
   engagement-state signal, and combining both sources would double-count
   one underlying event. ``label`` falls back to the raw ``chunk_id``
   string: Module 8 has no chunk title text available (that lives with
   Module 2's content metadata) — a known limitation, not a bug.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .metrics import INTERVENTION_TYPES, METRIC_VERSION

DATA_QUALITY_FLAGS = (
    "insufficient_sessions",
    "sparse_engagement",
    "inconsistent_metric_versions",
    "missing_intervention_outcomes",
    "incomplete_assistant_metadata",
    "insufficient_critical_section_data",
)


@dataclass(frozen=True)
class LearningProfileConfig:
    """Versioned thresholds used by learning-profile aggregation.

    Kept separate from ``metrics.MetricConfig`` (which governs single-session
    calculation) since these thresholds govern a different calculation with
    its own reproducibility needs — see CLAUDE.md 6.5 rule #4.
    """

    minimum_sessions_for_profile: int = 2
    minimum_sessions_for_trend: int = 3
    trend_focus_threshold_points: float = 5.0
    trend_recovery_threshold_rate: float = 0.15
    minimum_recurring_session_count: int = 2
    minimum_evidence_count_for_effective_support: int = 3
    effective_support_min_rate: float = 0.6
    majority_flag_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.minimum_sessions_for_profile < 1:
            raise ValueError("minimum_sessions_for_profile must be at least one")
        if self.minimum_sessions_for_trend < 1:
            raise ValueError("minimum_sessions_for_trend must be at least one")
        if self.minimum_recurring_session_count < 1:
            raise ValueError("minimum_recurring_session_count must be at least one")
        if self.minimum_evidence_count_for_effective_support < 1:
            raise ValueError(
                "minimum_evidence_count_for_effective_support must be at least one"
            )
        if not 0 <= self.effective_support_min_rate <= 1:
            raise ValueError("effective_support_min_rate must be between zero and one")
        if not 0 <= self.majority_flag_threshold <= 1:
            raise ValueError("majority_flag_threshold must be between zero and one")


DEFAULT_LEARNING_PROFILE_CONFIG = LearningProfileConfig()


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    else:
        raise TypeError("Expected an ISO 8601 string or datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Analytics timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).isoformat()
    return normalized.replace("+00:00", "Z")


def _round(value: float) -> float:
    return round(value, 6)


def _mean(values: Sequence[float]) -> float | None:
    values = list(values)
    if not values:
        return None
    return _round(sum(values) / len(values))


def _empty_profile(user_id: str, computed_at_str: str) -> dict[str, Any]:
    """The zero-session shape. Matches ``routes._placeholder_learning_profile``
    field-for-field, deliberately: that placeholder was designed to be the
    "no profile yet" state, which is exactly what zero input sessions means.
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
        "computed_at": computed_at_str,
    }


def _trend_from_series(
    values: Sequence[float],
    *,
    minimum_sessions: int,
    threshold: float,
) -> str:
    """Compare the first half of a chronological series to the second half.

    Below ``minimum_sessions`` qualifying data points, always
    ``"insufficient_data"`` — per CLAUDE.md 6.5 rule #7, a trend is never
    presented off too few points, and a two-point "trend" is not a pattern.
    """

    values = list(values)
    if len(values) < minimum_sessions:
        return "insufficient_data"
    midpoint = len(values) // 2
    first_half = values[:midpoint]
    second_half = values[midpoint:]
    first_mean = sum(first_half) / len(first_half)
    second_mean = sum(second_half) / len(second_half)
    difference = second_mean - first_mean
    if difference > threshold:
        return "improving"
    if difference < -threshold:
        return "declining"
    return "stable"


def _evaluable_counts(effective: int, ineffective: int, unknown: int) -> dict[str, Any]:
    evaluable = effective + ineffective
    return {
        "total_count": effective + ineffective + unknown,
        "effective_count": effective,
        "ineffective_count": ineffective,
        "unknown_outcome_count": unknown,
        "effectiveness_rate": _round(effective / evaluable) if evaluable else None,
    }


def _aggregate_intervention_effectiveness(
    summaries: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"effective": 0, "ineffective": 0, "unknown": 0}
    )
    for summary in summaries:
        for entry in summary.get("intervention_metrics", {}).get("by_type", []) or []:
            bucket = totals[entry["intervention_type"]]
            bucket["effective"] += entry.get("effective_count", 0) or 0
            bucket["ineffective"] += entry.get("ineffective_count", 0) or 0
            bucket["unknown"] += entry.get("unknown_outcome_count", 0) or 0

    result = []
    for intervention_type in INTERVENTION_TYPES:
        if intervention_type not in totals:
            continue
        counts = totals[intervention_type]
        item = {"intervention_type": intervention_type}
        item.update(
            _evaluable_counts(counts["effective"], counts["ineffective"], counts["unknown"])
        )
        result.append(item)
    return result


def _effective_support_methods(
    effectiveness_by_type: Sequence[Mapping[str, Any]], config: LearningProfileConfig
) -> list[dict[str, Any]]:
    """Filter cross-session effectiveness down to a cautious "worth
    recommending" shortlist — see module docstring point 2.
    """

    methods = []
    for entry in effectiveness_by_type:
        evaluable = entry["effective_count"] + entry["ineffective_count"]
        rate = entry["effectiveness_rate"]
        if evaluable < config.minimum_evidence_count_for_effective_support:
            continue
        if rate is None or rate < config.effective_support_min_rate:
            continue
        methods.append(
            {
                "intervention_type": entry["intervention_type"],
                "times_used": entry["total_count"],
                "effective_count": entry["effective_count"],
                "effectiveness_rate": rate,
            }
        )
    return methods


def _assistant_usage_patterns(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sessions_with_use = 0
    total_learner_messages = 0
    typed_total = 0
    voice_total = 0
    suggested_total = 0

    for summary in summaries:
        usage = summary.get("assistant_usage", {}) or {}
        if (usage.get("total_event_count") or 0) > 0:
            sessions_with_use += 1
        total_learner_messages += usage.get("learner_message_count", 0) or 0
        typed_total += usage.get("typed_input_count", 0) or 0
        voice_total += usage.get("voice_input_count", 0) or 0
        suggested_total += usage.get("suggested_question_count", 0) or 0

    nonzero_modes = [
        count > 0 for count in (typed_total, voice_total, suggested_total)
    ].count(True)
    if nonzero_modes == 0:
        preferred = "unknown"
    elif nonzero_modes > 1:
        preferred = "mixed"
    elif typed_total > 0:
        preferred = "typed"
    elif voice_total > 0:
        preferred = "voice"
    else:
        preferred = "suggested_question"

    return {
        "sessions_with_assistant_use": sessions_with_use,
        "average_learner_messages_per_session": (
            _round(total_learner_messages / len(summaries)) if summaries else None
        ),
        "typed_input_count": typed_total,
        "voice_input_count": voice_total,
        "suggested_question_count": suggested_total,
        "preferred_input_mode": preferred,
    }


def _recurring_difficulty_areas(
    summaries: Sequence[Mapping[str, Any]], config: LearningProfileConfig
) -> list[dict[str, Any]]:
    difficulty_states = {"struggling", "fatigued"}
    # area_key -> {"content_id", "chunk_id", "sessions": set(session_id), "occurrences": int}
    areas: dict[tuple[str | None, str], dict[str, Any]] = {}

    for summary in summaries:
        content_id = summary.get("content_id")
        session_id = summary.get("session_id")
        seen_chunks_this_session: set[str] = set()
        for segment in summary.get("timeline_segments", []) or []:
            chunk_id = segment.get("chunk_id")
            if chunk_id is None or segment.get("state") not in difficulty_states:
                continue
            key = (content_id, chunk_id)
            area = areas.setdefault(
                key,
                {
                    "content_id": content_id,
                    "chunk_id": chunk_id,
                    "sessions": set(),
                    "occurrences": 0,
                },
            )
            area["occurrences"] += 1
            if session_id is not None:
                area["sessions"].add(session_id)
            seen_chunks_this_session.add(chunk_id)

    result = []
    for (content_id, chunk_id), area in areas.items():
        session_count = len(area["sessions"])
        if session_count < config.minimum_recurring_session_count:
            continue
        result.append(
            {
                "area_key": f"{content_id}:{chunk_id}",
                "label": chunk_id,
                "content_id": content_id,
                "chunk_id": chunk_id,
                "session_count": session_count,
                "occurrence_count": area["occurrences"],
            }
        )
    result.sort(key=lambda item: (-item["session_count"], -item["occurrence_count"]))
    return result


def _critical_section_aggregates(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sections_observed = 0
    sessions_with_critical_sections = 0
    engagement_rates: list[float] = []
    focus_percentages: list[float] = []

    for summary in summaries:
        critical = summary.get("critical_section_engagement", {}) or {}
        count = critical.get("critical_section_count", 0) or 0
        sections_observed += count
        if count > 0:
            sessions_with_critical_sections += 1
            if critical.get("engagement_rate") is not None:
                engagement_rates.append(critical["engagement_rate"])
            focused_percentage = (
                summary.get("engagement_distribution", {}).get("focused", {}).get("percentage")
            )
            if focused_percentage is not None:
                focus_percentages.append(focused_percentage)

    return {
        "sections_observed": sections_observed,
        "sessions_with_critical_sections": sessions_with_critical_sections,
        "average_engagement_rate": _mean(engagement_rates),
        "average_focus_percentage": _mean(focus_percentages),
    }


def _majority_flagged(
    summaries: Sequence[Mapping[str, Any]],
    flag: str,
    *,
    subset: Sequence[Mapping[str, Any]] | None = None,
    threshold: float,
) -> bool:
    candidates = list(subset) if subset is not None else list(summaries)
    if not candidates:
        return False
    flagged = sum(
        1 for summary in candidates if flag in (summary.get("data_quality", {}).get("flags") or [])
    )
    return flagged / len(candidates) >= threshold


def _profile_data_quality(
    summaries: Sequence[Mapping[str, Any]],
    *,
    sessions_analyzed: int,
    sessions_with_critical_sections: int,
    metric_versions: set[str],
    config: LearningProfileConfig,
) -> dict[str, Any]:
    sufficient = sum(
        1
        for summary in summaries
        if (summary.get("data_quality", {}) or {}).get("has_sufficient_data") is True
    )
    coverage_rates = [
        summary["data_quality"]["event_coverage_rate"]
        for summary in summaries
        if (summary.get("data_quality", {}) or {}).get("event_coverage_rate") is not None
    ]

    sessions_with_interventions = [
        summary
        for summary in summaries
        if (summary.get("intervention_metrics", {}) or {}).get("total_count", 0)
    ]
    sessions_with_assistant_use = [
        summary
        for summary in summaries
        if (summary.get("assistant_usage", {}) or {}).get("total_event_count", 0)
    ]

    flags: list[str] = []
    if sessions_analyzed < config.minimum_sessions_for_profile:
        flags.append("insufficient_sessions")
    if _majority_flagged(
        summaries, "sparse_engagement", threshold=config.majority_flag_threshold
    ):
        flags.append("sparse_engagement")
    if len(metric_versions) > 1:
        flags.append("inconsistent_metric_versions")
    if _majority_flagged(
        summaries,
        "missing_intervention_outcomes",
        subset=sessions_with_interventions,
        threshold=config.majority_flag_threshold,
    ):
        flags.append("missing_intervention_outcomes")
    if _majority_flagged(
        summaries,
        "incomplete_assistant_metadata",
        subset=sessions_with_assistant_use,
        threshold=config.majority_flag_threshold,
    ):
        flags.append("incomplete_assistant_metadata")
    if sessions_analyzed > 0 and sessions_with_critical_sections == 0:
        flags.append("insufficient_critical_section_data")

    ordered_flags = [flag for flag in DATA_QUALITY_FLAGS if flag in flags]

    return {
        "sessions_with_sufficient_data": sufficient,
        "average_event_coverage_rate": _mean(coverage_rates),
        "flags": ordered_flags,
    }


def build_learning_profile(
    user_id: str,
    session_summaries: Sequence[Mapping[str, Any]],
    *,
    computed_at: str | datetime,
    config: LearningProfileConfig = DEFAULT_LEARNING_PROFILE_CONFIG,
) -> dict[str, Any]:
    """Build one contract-compatible, deterministic multi-session learning
    profile for ``user_id`` from their completed session summaries.

    ``computed_at`` is injected (never read from the system clock) so
    repeated calls against identical input produce identical output — the
    same testability rule ``build_session_summary`` (Issue #26) follows.

    Recalculation is deterministic: the same summaries, in any input order,
    at the same config, always produce the same profile (summaries are
    sorted internally by ``completed_at`` before anything is computed).
    """

    computed_at_str = _format_datetime(_parse_datetime(computed_at))
    summaries = sorted(session_summaries, key=lambda summary: summary.get("completed_at") or "")
    sessions_analyzed = len(summaries)

    if sessions_analyzed == 0:
        return _empty_profile(user_id, computed_at_str)

    metric_versions = {
        summary.get("metric_version") for summary in summaries if summary.get("metric_version")
    }

    completed_ats = [summary["completed_at"] for summary in summaries]
    analysis_date_range = {"started_at": completed_ats[0], "ended_at": completed_ats[-1]}

    average_session_duration_seconds = _mean(
        [summary["duration_seconds"] for summary in summaries]
    )
    focus_percentages = [
        summary["engagement_distribution"]["focused"]["percentage"] for summary in summaries
    ]
    average_focus_percentage = _mean(focus_percentages)
    focus_trend = _trend_from_series(
        focus_percentages,
        minimum_sessions=config.minimum_sessions_for_trend,
        threshold=config.trend_focus_threshold_points,
    )

    recovery_rates = [
        summary["recovery_metrics"]["recovery_rate"]
        for summary in summaries
        if summary.get("recovery_metrics", {}).get("recovery_rate") is not None
    ]
    recovery_trend = _trend_from_series(
        recovery_rates,
        minimum_sessions=config.minimum_sessions_for_trend,
        threshold=config.trend_recovery_threshold_rate,
    )

    intervention_effectiveness_by_type = _aggregate_intervention_effectiveness(summaries)
    effective_support_methods = _effective_support_methods(
        intervention_effectiveness_by_type, config
    )
    assistant_usage_patterns = _assistant_usage_patterns(summaries)
    recurring_difficulty_areas = _recurring_difficulty_areas(summaries, config)
    critical_section_aggregates = _critical_section_aggregates(summaries)

    data_quality = _profile_data_quality(
        summaries,
        sessions_analyzed=sessions_analyzed,
        sessions_with_critical_sections=critical_section_aggregates[
            "sessions_with_critical_sections"
        ],
        metric_versions=metric_versions,
        config=config,
    )

    return {
        "schema_version": "1.0",
        "metric_version": METRIC_VERSION,
        "user_id": user_id,
        "sessions_analyzed": sessions_analyzed,
        "analysis_date_range": analysis_date_range,
        "average_session_duration_seconds": average_session_duration_seconds,
        "average_focus_percentage": average_focus_percentage,
        "focus_trend": focus_trend,
        "recovery_trend": recovery_trend,
        "intervention_effectiveness_by_type": intervention_effectiveness_by_type,
        "assistant_usage_patterns": assistant_usage_patterns,
        "recurring_difficulty_areas": recurring_difficulty_areas,
        "effective_support_methods": effective_support_methods,
        "critical_section_aggregates": critical_section_aggregates,
        "data_quality": data_quality,
        "computed_at": computed_at_str,
    }

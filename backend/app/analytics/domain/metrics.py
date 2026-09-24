"""Deterministic, infrastructure-independent Module 8 metric calculations.

The public functions accept ordinary mappings and sequences. They deliberately do
not import web frameworks, database clients, model SDKs, or frontend code.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence


METRIC_VERSION = "1.0"
ENGAGEMENT_STATES = (
    "focused",
    "drifting",
    "struggling",
    "fatigued",
    "recovered",
    "unknown",
)
INTERVENTION_TYPES = (
    "simplify_content",
    "bullet_summary",
    "break_suggestion",
    "assistant_help_prompt",
    "other",
)
SESSION_QUALITY_FLAGS = (
    "sparse_engagement",
    "missing_intervention_outcomes",
    "incomplete_assistant_metadata",
    "excessive_unknown_gaps",
    "missing_chunk_context",
    "incomplete_session_timing",
    "no_webcam_data",
)
WEBCAM_DERIVED_FIELDS = (
    "gaze_x",
    "gaze_y",
    "blink_rate",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "eye_openness",
    "brow_raise",
    "inter_brow",
)


@dataclass(frozen=True)
class MetricConfig:
    """Versioned thresholds used by all metric calculations."""

    metric_version: str = METRIC_VERSION
    expected_sampling_interval_seconds: float = 5.0
    gap_tolerance_seconds: float = 10.0
    minimum_focused_period_seconds: float = 5.0
    smooth_isolated_state_events: bool = True
    isolated_noise_max_duration_seconds: float = 2.0
    isolated_noise_confidence_threshold: float = 0.4
    smoothable_noise_states: tuple[str, ...] = ("drifting",)
    deep_thinking_counts_as_focused: bool = True
    deep_thinking_promotable_states: tuple[str, ...] = ("drifting",)
    recovery_window_seconds: float = 120.0
    recovery_confirmation_samples: int = 2
    minimum_event_coverage_rate: float = 0.8
    excessive_unknown_rate: float = 0.2
    automatic_intervention_types: tuple[str, ...] = (
        "simplify_content",
        "bullet_summary",
    )
    learner_initiated_intervention_types: tuple[str, ...] = (
        "break_suggestion",
        "assistant_help_prompt",
        "other",
    )
    automatic_recovery_start_statuses: tuple[str, ...] = (
        "displayed",
        "accepted",
        "completed",
    )
    learner_recovery_start_statuses: tuple[str, ...] = (
        "accepted",
        "completed",
    )

    def __post_init__(self) -> None:
        positive_fields = (
            self.expected_sampling_interval_seconds,
            self.gap_tolerance_seconds,
            self.minimum_focused_period_seconds,
            self.isolated_noise_max_duration_seconds,
            self.recovery_window_seconds,
        )
        if any(value <= 0 for value in positive_fields):
            raise ValueError("Metric timing thresholds must be positive")
        if self.expected_sampling_interval_seconds > self.gap_tolerance_seconds:
            raise ValueError("Expected sampling interval must not exceed gap tolerance")
        if self.recovery_confirmation_samples < 1:
            raise ValueError("recovery_confirmation_samples must be at least one")
        if not 0 <= self.isolated_noise_confidence_threshold <= 1:
            raise ValueError("isolated_noise_confidence_threshold must be between zero and one")
        if not 0 <= self.minimum_event_coverage_rate <= 1:
            raise ValueError("minimum_event_coverage_rate must be between zero and one")
        if not 0 <= self.excessive_unknown_rate <= 1:
            raise ValueError("excessive_unknown_rate must be between zero and one")


DEFAULT_CONFIG = MetricConfig()


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


def _seconds(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds())


def _round_number(value: float) -> float:
    return round(value, 6)


def _normalized_state(event: Mapping[str, Any], config: MetricConfig) -> str:
    state = event.get("state", "unknown")
    if state not in ENGAGEMENT_STATES:
        state = "unknown"
    if (
        config.deep_thinking_counts_as_focused
        and event.get("deep_thinking_detected")
        and state in config.deep_thinking_promotable_states
    ):
        return "focused"
    return state


def _prepare_engagement_events(
    events: Sequence[Mapping[str, Any]],
    session_start: datetime,
    session_end: datetime,
    config: MetricConfig,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for event in events:
        timestamp = _parse_datetime(event["timestamp"])
        if timestamp < session_start or timestamp > session_end:
            continue
        prepared.append(
            {
                "event": event,
                "timestamp": timestamp,
                "state": _normalized_state(event, config),
                "confidence": float(event.get("confidence", 0.0)),
                "chunk_id": event.get("chunk_id"),
            }
        )
    by_event_id: dict[str, dict[str, Any]] = {}
    without_event_id: list[dict[str, Any]] = []
    for item in prepared:
        event_id = item["event"].get("event_id")
        if not event_id:
            without_event_id.append(item)
            continue
        choice_key = (
            item["timestamp"],
            item["confidence"],
            item["state"],
            str(item["chunk_id"]),
        )
        existing = by_event_id.get(event_id)
        if existing is None:
            by_event_id[event_id] = item
        else:
            existing_key = (
                existing["timestamp"],
                existing["confidence"],
                existing["state"],
                str(existing["chunk_id"]),
            )
            if choice_key > existing_key:
                by_event_id[event_id] = item
    deduplicated = list(by_event_id.values()) + without_event_id

    by_timestamp: dict[datetime, dict[str, Any]] = {}
    for item in deduplicated:
        existing = by_timestamp.get(item["timestamp"])
        choice_key = (
            item["confidence"],
            item["event"].get("event_id", ""),
            item["state"],
            str(item["chunk_id"]),
        )
        if existing is None:
            by_timestamp[item["timestamp"]] = item
        else:
            existing_key = (
                existing["confidence"],
                existing["event"].get("event_id", ""),
                existing["state"],
                str(existing["chunk_id"]),
            )
            if choice_key > existing_key:
                by_timestamp[item["timestamp"]] = item
    prepared = sorted(
        by_timestamp.values(),
        key=lambda item: (item["timestamp"], item["event"].get("event_id", "")),
    )

    if config.smooth_isolated_state_events and len(prepared) >= 3:
        original_states = [item["state"] for item in prepared]
        for index in range(1, len(prepared) - 1):
            previous = prepared[index - 1]
            current = prepared[index]
            following = prepared[index + 1]
            previous_gap = _seconds(previous["timestamp"], current["timestamp"])
            noise_duration = _seconds(current["timestamp"], following["timestamp"])
            if (
                original_states[index - 1] == original_states[index + 1]
                and original_states[index] != original_states[index - 1]
                and previous_gap <= config.gap_tolerance_seconds
                and noise_duration <= config.isolated_noise_max_duration_seconds
                and original_states[index] in config.smoothable_noise_states
                and current["confidence"] < config.isolated_noise_confidence_threshold
                and previous["chunk_id"] == current["chunk_id"] == following["chunk_id"]
            ):
                current["state"] = original_states[index - 1]
                current["confidence"] = min(
                    previous["confidence"], following["confidence"]
                )
    return prepared


def _append_segment(
    segments: list[dict[str, Any]],
    state: str,
    start: datetime,
    end: datetime,
    confidence: float | None,
    chunk_id: str | None,
) -> None:
    duration = _seconds(start, end)
    if duration <= 0:
        return
    if (
        segments
        and segments[-1]["state"] == state
        and segments[-1]["chunk_id"] == chunk_id
        and segments[-1]["_ended_at"] == start
    ):
        segment = segments[-1]
        previous_duration = segment["duration_seconds"]
        total_duration = previous_duration + duration
        if confidence is not None and segment["average_confidence"] is not None:
            segment["average_confidence"] = (
                segment["average_confidence"] * previous_duration + confidence * duration
            ) / total_duration
        elif confidence is not None:
            segment["average_confidence"] = confidence
        segment["_ended_at"] = end
        segment["ended_at"] = _format_datetime(end)
        segment["duration_seconds"] = total_duration
        return

    segments.append(
        {
            "started_at": _format_datetime(start),
            "ended_at": _format_datetime(end),
            "duration_seconds": duration,
            "state": state,
            "average_confidence": confidence,
            "chunk_id": chunk_id,
            "_ended_at": end,
        }
    )


def segment_engagement_timeline(
    events: Sequence[Mapping[str, Any]],
    session_start: str | datetime,
    session_end: str | datetime,
    config: MetricConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """Create a complete timeline, representing long or missing gaps as unknown."""

    start = _parse_datetime(session_start)
    end = _parse_datetime(session_end)
    if end < start:
        raise ValueError("session_end must not precede session_start")
    if end == start:
        return []

    prepared = _prepare_engagement_events(events, start, end, config)
    segments: list[dict[str, Any]] = []
    if not prepared:
        _append_segment(segments, "unknown", start, end, None, None)
    else:
        first_timestamp = prepared[0]["timestamp"]
        _append_segment(segments, "unknown", start, first_timestamp, None, None)
        for index, item in enumerate(prepared):
            timestamp = item["timestamp"]
            next_timestamp = (
                prepared[index + 1]["timestamp"] if index + 1 < len(prepared) else end
            )
            interval_end = min(next_timestamp, end)
            interval_seconds = _seconds(timestamp, interval_end)
            if interval_seconds <= config.gap_tolerance_seconds:
                known_end = interval_end
            else:
                known_end = min(
                    timestamp + timedelta(seconds=config.expected_sampling_interval_seconds),
                    interval_end,
                )
            _append_segment(
                segments,
                item["state"],
                timestamp,
                known_end,
                item["confidence"],
                item["chunk_id"],
            )
            _append_segment(segments, "unknown", known_end, interval_end, None, None)

    output: list[dict[str, Any]] = []
    for segment in segments:
        output.append(
            {
                "started_at": segment["started_at"],
                "ended_at": segment["ended_at"],
                "duration_seconds": _round_number(segment["duration_seconds"]),
                "state": segment["state"],
                "average_confidence": (
                    None
                    if segment["average_confidence"] is None
                    else _round_number(segment["average_confidence"])
                ),
                "chunk_id": segment["chunk_id"],
            }
        )
    return output


def calculate_engagement_distribution(
    timeline_segments: Sequence[Mapping[str, Any]],
    session_duration_seconds: float,
) -> dict[str, dict[str, float]]:
    """Calculate duration and 0-100 percentage for every engagement state."""

    durations = {state: 0.0 for state in ENGAGEMENT_STATES}
    for segment in timeline_segments:
        state = segment.get("state", "unknown")
        state = state if state in durations else "unknown"
        durations[state] += max(0.0, float(segment.get("duration_seconds", 0.0)))

    accounted = sum(durations.values())
    if session_duration_seconds > accounted:
        durations["unknown"] += session_duration_seconds - accounted
    elif accounted > session_duration_seconds:
        excess = accounted - session_duration_seconds
        unknown_reduction = min(excess, durations["unknown"])
        durations["unknown"] -= unknown_reduction
        excess -= unknown_reduction
        if excess > 0:
            known_total = sum(
                duration for state, duration in durations.items() if state != "unknown"
            )
            scale = max(0.0, (known_total - excess) / known_total) if known_total else 0.0
            for state in ENGAGEMENT_STATES:
                if state != "unknown":
                    durations[state] *= scale
    denominator = max(0.0, session_duration_seconds)
    rounded_durations = {
        state: _round_number(duration) for state, duration in durations.items()
    }
    if denominator > 0:
        duration_delta = _round_number(denominator - sum(rounded_durations.values()))
        adjustment_state = max(ENGAGEMENT_STATES, key=lambda state: rounded_durations[state])
        rounded_durations[adjustment_state] = _round_number(
            rounded_durations[adjustment_state] + duration_delta
        )
    result = {
        state: {
            "duration_seconds": duration,
            "percentage": (
                _round_number(duration / denominator * 100.0) if denominator > 0 else 0.0
            ),
        }
        for state, duration in rounded_durations.items()
    }
    if denominator > 0:
        percentage_delta = _round_number(
            100.0 - sum(item["percentage"] for item in result.values())
        )
        adjustment_state = max(
            ENGAGEMENT_STATES,
            key=lambda state: result[state]["duration_seconds"],
        )
        result[adjustment_state]["percentage"] = _round_number(
            result[adjustment_state]["percentage"] + percentage_delta
        )
    return result


def find_longest_focused_period(
    timeline_segments: Sequence[Mapping[str, Any]],
    config: MetricConfig = DEFAULT_CONFIG,
) -> dict[str, Any] | None:
    """Return the longest valid continuous focused segment, or None."""

    periods: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for segment in timeline_segments:
        duration = float(segment.get("duration_seconds", 0.0))
        if segment.get("state") != "focused" or duration <= 0:
            if current is not None:
                periods.append(current)
                current = None
            continue
        started_at = _parse_datetime(segment["started_at"])
        ended_at = _parse_datetime(segment["ended_at"])
        if current is not None and current["_ended_at"] == started_at:
            current["_ended_at"] = ended_at
            current["ended_at"] = segment["ended_at"]
            current["duration_seconds"] += duration
            current["_chunk_ids"].add(segment.get("chunk_id"))
        else:
            if current is not None:
                periods.append(current)
            current = {
                "started_at": segment["started_at"],
                "ended_at": segment["ended_at"],
                "duration_seconds": duration,
                "_ended_at": ended_at,
                "_chunk_ids": {segment.get("chunk_id")},
            }
    if current is not None:
        periods.append(current)

    valid_periods = [
        period
        for period in periods
        if period["duration_seconds"] >= config.minimum_focused_period_seconds
    ]
    if not valid_periods:
        return None
    longest = max(
        valid_periods,
        key=lambda period: (
            float(period["duration_seconds"]),
            -_parse_datetime(period["started_at"]).timestamp(),
        ),
    )
    chunk_ids = longest["_chunk_ids"]
    return {
        "started_at": longest["started_at"],
        "ended_at": longest["ended_at"],
        "duration_seconds": _round_number(float(longest["duration_seconds"])),
        "chunk_id": next(iter(chunk_ids)) if len(chunk_ids) == 1 else None,
    }


def _eligible_interventions(
    interventions: Sequence[Mapping[str, Any]], config: MetricConfig
) -> list[Mapping[str, Any]]:
    eligible = [
        intervention
        for intervention in interventions
        if _recovery_start_time(intervention, config) is not None
    ]
    return sorted(
        eligible,
        key=lambda item: (_parse_datetime(item["timestamp"]), item.get("intervention_id", "")),
    )


def _recovery_start_time(
    intervention: Mapping[str, Any], config: MetricConfig
) -> datetime | None:
    """Return the versioned lifecycle point from which recovery is observed.

    Automatic content adaptations can be experienced once displayed. Supports that
    require learner action become eligible only after acceptance or completion.
    """

    intervention_type = intervention.get("intervention_type")
    status = intervention.get("delivery_status")
    if intervention_type in config.automatic_intervention_types:
        eligible_statuses = config.automatic_recovery_start_statuses
    elif intervention_type in config.learner_initiated_intervention_types:
        eligible_statuses = config.learner_recovery_start_statuses
    else:
        return None
    if status not in eligible_statuses:
        return None
    return _parse_datetime(intervention["timestamp"])


def _observed_recovery(
    intervention: Mapping[str, Any],
    engagement_events: Sequence[Mapping[str, Any]],
    start: datetime,
    limit: datetime,
    competing_start: datetime | None,
    config: MetricConfig,
) -> tuple[datetime | None, float | None]:
    explicit_timestamp = intervention.get("recovery_timestamp")
    if explicit_timestamp is not None:
        recovered_at = _parse_datetime(explicit_timestamp)
        if start < recovered_at <= limit and (
            competing_start is None or recovered_at < competing_start
        ):
            duration_seconds = _seconds(start, recovered_at)
            if duration_seconds > 0:
                return recovered_at, duration_seconds

    candidates = []
    for event in engagement_events:
        timestamp = _parse_datetime(event["timestamp"])
        if timestamp < start:
            continue
        if timestamp > limit or (competing_start is not None and timestamp >= competing_start):
            continue
        candidates.append((timestamp, _normalized_state(event, config), event.get("event_id", "")))
    candidates.sort(key=lambda item: (item[0], item[2]))

    sequence_start: datetime | None = None
    previous_timestamp: datetime | None = None
    confirmation_count = 0
    for timestamp, state, _ in candidates:
        qualifies = state in {"focused", "recovered"}
        continuous = (
            previous_timestamp is not None
            and _seconds(previous_timestamp, timestamp) <= config.gap_tolerance_seconds
        )
        if qualifies:
            if sequence_start is None or not continuous:
                sequence_start = timestamp
                confirmation_count = 1
            else:
                confirmation_count += 1
            if confirmation_count >= config.recovery_confirmation_samples:
                duration = _seconds(start, sequence_start)
                if duration > 0:
                    return sequence_start, duration
        else:
            sequence_start = None
            confirmation_count = 0
        previous_timestamp = timestamp
    return None, None


def calculate_recoveries(
    interventions: Sequence[Mapping[str, Any]],
    engagement_events: Sequence[Mapping[str, Any]],
    session_end: str | datetime,
    config: MetricConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """Calculate per-intervention recovery without attributing across overlaps."""

    end = _parse_datetime(session_end)
    eligible = _eligible_interventions(interventions, config)
    recoveries: list[dict[str, Any]] = []
    for index, intervention in enumerate(eligible):
        start = _recovery_start_time(intervention, config)
        if start is None:
            continue
        if start > end:
            continue
        competing_start = (
            _parse_datetime(eligible[index + 1]["timestamp"])
            if index + 1 < len(eligible)
            else None
        )
        limit = min(end, start + timedelta(seconds=config.recovery_window_seconds))
        if competing_start is not None:
            limit = min(limit, competing_start)
        recovered_at, duration = _observed_recovery(
            intervention,
            engagement_events,
            start,
            limit,
            competing_start,
            config,
        )
        recoveries.append(
            {
                "intervention_id": intervention["intervention_id"],
                "recovery_timestamp": (
                    _format_datetime(recovered_at) if recovered_at is not None else None
                ),
                "recovery_duration_seconds": (
                    _round_number(duration) if duration is not None else None
                ),
                "recovered": recovered_at is not None,
            }
        )
    return recoveries


def calculate_recovery_metrics(
    recovery_results: Sequence[Mapping[str, Any]],
) -> dict[str, int | float | None]:
    eligible_count = len(recovery_results)
    durations = [
        float(result["recovery_duration_seconds"])
        for result in recovery_results
        if result.get("recovered") and result.get("recovery_duration_seconds") is not None
    ]
    recovered_count = len(durations)
    return {
        "eligible_intervention_count": eligible_count,
        "recovered_intervention_count": recovered_count,
        "recovery_rate": (
            _round_number(recovered_count / eligible_count) if eligible_count else None
        ),
        "average_recovery_time_seconds": (
            _round_number(sum(durations) / recovered_count) if recovered_count else None
        ),
    }


def classify_intervention_effectiveness(
    intervention: Mapping[str, Any], recovery_result: Mapping[str, Any] | None = None
) -> str:
    """Classify observed benefit while preserving ambiguous outcomes as unknown."""

    if intervention.get("helped") is True:
        return "effective"
    if intervention.get("helped") is False:
        return "ineffective"
    outcome = intervention.get("outcome")
    if outcome in {"recovered", "improved"}:
        return "effective"
    if outcome in {"unchanged", "worsened"}:
        return "ineffective"
    if recovery_result is not None and recovery_result.get("recovered"):
        return "effective"
    return "unknown"


def _metric_counts(classifications: Iterable[str]) -> dict[str, int | float | None]:
    values = list(classifications)
    effective = values.count("effective")
    ineffective = values.count("ineffective")
    unknown = values.count("unknown")
    evaluable = effective + ineffective
    return {
        "total_count": len(values),
        "effective_count": effective,
        "ineffective_count": ineffective,
        "unknown_outcome_count": unknown,
        "effectiveness_rate": _round_number(effective / evaluable) if evaluable else None,
    }


def calculate_intervention_metrics(
    interventions: Sequence[Mapping[str, Any]],
    recovery_results: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    recovery_by_id = {
        result["intervention_id"]: result for result in recovery_results
    }
    classified = [
        (
            intervention,
            classify_intervention_effectiveness(
                intervention, recovery_by_id.get(intervention.get("intervention_id"))
            ),
        )
        for intervention in interventions
    ]
    metrics = _metric_counts(classification for _, classification in classified)
    grouped: dict[str, list[str]] = defaultdict(list)
    for intervention, classification in classified:
        grouped[intervention.get("intervention_type", "other")].append(classification)
    by_type = []
    for intervention_type in INTERVENTION_TYPES:
        if intervention_type not in grouped:
            continue
        item = {"intervention_type": intervention_type}
        item.update(_metric_counts(grouped[intervention_type]))
        by_type.append(item)
    metrics["by_type"] = by_type
    return metrics


def calculate_assistant_usage(
    assistant_events: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Count metadata events; successful interactions are completed responses.

    The contract has no request/correlation ID, so learner messages cannot be paired
    reliably. A successful assistant-direction response is the conservative proxy.
    """

    learner_events = [event for event in assistant_events if event.get("direction") == "learner"]
    assistant_responses = [
        event for event in assistant_events if event.get("direction") == "assistant"
    ]
    return {
        "total_event_count": len(assistant_events),
        "learner_message_count": len(learner_events),
        "assistant_message_count": len(assistant_responses),
        "typed_input_count": sum(event.get("input_mode") == "typed" for event in learner_events),
        "voice_input_count": sum(event.get("input_mode") == "voice" for event in learner_events),
        "suggested_question_count": sum(
            event.get("input_mode") == "suggested_question"
            or event.get("suggested_question_used") is True
            for event in learner_events
        ),
        "text_response_count": sum(
            event.get("response_mode") in {"text", "mixed"} for event in assistant_responses
        ),
        "voice_response_count": sum(
            event.get("response_mode") in {"voice", "mixed"} for event in assistant_responses
        ),
        "successful_interaction_count": sum(
            event.get("direction") == "assistant" and event.get("status") == "success"
            for event in assistant_events
        ),
        "error_count": sum(event.get("status") == "error" for event in assistant_events),
    }


def _assistant_metadata_incomplete(event: Mapping[str, Any]) -> bool:
    required = {
        "event_id",
        "session_id",
        "user_id",
        "timestamp",
        "direction",
        "input_mode",
        "response_mode",
        "intent",
        "learner_signal",
        "suggested_question_used",
        "status",
    }
    if any(field not in event for field in required):
        return True
    if event.get("direction") == "assistant":
        return (
            event.get("input_mode") != "not_applicable"
            or event.get("suggested_question_used") is not False
        )
    if event.get("direction") == "learner":
        return event.get("response_mode") != "not_applicable"
    return True


def _critical_section_metrics(
    timeline_segments: Sequence[Mapping[str, Any]],
    chunk_context: Sequence[Mapping[str, Any]] | None,
) -> tuple[dict[str, int | float | None], int]:
    chunks = list(chunk_context or ())
    critical_ids = {
        chunk["chunk_id"] for chunk in chunks if chunk.get("is_critical") is True
    }
    engaged_ids = {
        segment.get("chunk_id")
        for segment in timeline_segments
        if segment.get("chunk_id") in critical_ids
        and segment.get("state") in {"focused", "recovered"}
        and float(segment.get("duration_seconds", 0.0)) > 0
    }
    focused_duration = sum(
        float(segment.get("duration_seconds", 0.0))
        for segment in timeline_segments
        if segment.get("chunk_id") in critical_ids and segment.get("state") == "focused"
    )
    count = len(critical_ids)
    metrics = {
        "critical_section_count": count,
        "engaged_section_count": len(engaged_ids),
        "engagement_rate": _round_number(len(engaged_ids) / count) if count else None,
        "focused_duration_seconds": _round_number(focused_duration),
    }
    chunks_completed = sum(chunk.get("completed") is True for chunk in chunks)
    return metrics, chunks_completed


def _data_quality_metrics(
    session: Mapping[str, Any],
    engagement_events: Sequence[Mapping[str, Any]],
    intervention_events: Sequence[Mapping[str, Any]],
    intervention_metrics: Mapping[str, Any],
    assistant_events: Sequence[Mapping[str, Any]],
    distribution: Mapping[str, Mapping[str, float]],
    session_duration_seconds: float,
    timing_complete: bool,
    chunk_context: Sequence[Mapping[str, Any]] | None,
    config: MetricConfig,
) -> dict[str, Any]:
    unknown_duration = float(distribution["unknown"]["duration_seconds"])
    coverage_rate = (
        max(0.0, min(1.0, 1.0 - unknown_duration / session_duration_seconds))
        if session_duration_seconds > 0
        else None
    )
    flags: list[str] = []
    if coverage_rate is None or coverage_rate < config.minimum_event_coverage_rate:
        flags.append("sparse_engagement")
    if intervention_metrics["unknown_outcome_count"] > 0:
        flags.append("missing_intervention_outcomes")
    if any(_assistant_metadata_incomplete(event) for event in assistant_events):
        flags.append("incomplete_assistant_metadata")
    unknown_rate = (
        unknown_duration / session_duration_seconds if session_duration_seconds > 0 else 1.0
    )
    if unknown_rate > config.excessive_unknown_rate:
        flags.append("excessive_unknown_gaps")
    chunks = list(chunk_context or ())
    known_chunk_ids = {
        chunk.get("chunk_id") for chunk in chunks if chunk.get("chunk_id") is not None
    }
    contextual_events = list(engagement_events) + list(intervention_events) + list(
        assistant_events
    )
    if not known_chunk_ids or any(
        event.get("chunk_id") is None or event.get("chunk_id") not in known_chunk_ids
        for event in contextual_events
    ):
        flags.append("missing_chunk_context")
    if not timing_complete:
        flags.append("incomplete_session_timing")
    has_webcam_evidence = any(
        event.get("source") in {"lstm", "hybrid"}
        or any(event.get(field) is not None for field in WEBCAM_DERIVED_FIELDS)
        or event.get("gaze_regression_detected") is True
        or event.get("deep_thinking_detected") is True
        for event in engagement_events
    )
    if not has_webcam_evidence:
        flags.append("no_webcam_data")
    ordered_flags = [flag for flag in SESSION_QUALITY_FLAGS if flag in flags]
    invalidating = {
        "sparse_engagement",
        "excessive_unknown_gaps",
        "incomplete_session_timing",
    }
    return {
        "has_sufficient_data": not any(flag in invalidating for flag in ordered_flags),
        "event_coverage_rate": (
            _round_number(coverage_rate) if coverage_rate is not None else None
        ),
        "unknown_duration_seconds": _round_number(unknown_duration),
        "flags": ordered_flags,
    }


def _session_bounds(
    session: Mapping[str, Any],
) -> tuple[datetime, datetime, float, bool]:
    """Resolve wall-clock boundaries and the contract's active duration.

    A valid ``duration_seconds`` is authoritative for calculated distributions. The
    timestamps bound accepted events and provide an independent consistency check.
    """

    start = _parse_datetime(session["started_at"])
    ended_at = session.get("ended_at")
    supplied_duration = session.get("duration_seconds")
    duration_is_valid = (
        isinstance(supplied_duration, int)
        and not isinstance(supplied_duration, bool)
        and supplied_duration >= 0
    )
    if ended_at is not None:
        end = _parse_datetime(ended_at)
    elif duration_is_valid:
        end = start + timedelta(seconds=supplied_duration)
    else:
        raise ValueError("A completed session needs ended_at or duration_seconds")
    if end < start:
        raise ValueError("Session end must not precede session start")
    wall_duration = _seconds(start, end)
    analysis_duration = float(supplied_duration) if duration_is_valid else wall_duration
    timing_complete = (
        ended_at is not None
        and duration_is_valid
        and abs(analysis_duration - wall_duration) <= 1.0
    )
    return start, end, analysis_duration, timing_complete


def _events_within_bounds(
    events: Sequence[Mapping[str, Any]], start: datetime, end: datetime
) -> list[Mapping[str, Any]]:
    return [
        event
        for event in events
        if start <= _parse_datetime(event["timestamp"]) <= end
    ]


def _validate_event_scope(
    session: Mapping[str, Any], event_groups: Sequence[Sequence[Mapping[str, Any]]]
) -> None:
    for events in event_groups:
        for event in events:
            if event.get("session_id") != session["session_id"]:
                raise ValueError("All events must belong to the summarized session")
            if event.get("user_id") != session["user_id"]:
                raise ValueError("All events must belong to the summarized user")
            if event.get("content_id") not in {None, session["content_id"]}:
                raise ValueError("All events must belong to the summarized content")


def build_session_summary(
    session: Mapping[str, Any],
    engagement_events: Sequence[Mapping[str, Any]],
    intervention_events: Sequence[Mapping[str, Any]],
    assistant_events: Sequence[Mapping[str, Any]],
    *,
    computed_at: str | datetime,
    chunk_context: Sequence[Mapping[str, Any]] | None = None,
    config: MetricConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Build one contract-compatible, deterministic completed-session summary.

    ``computed_at`` is injected rather than read from the system clock so repeated
    calls with identical inputs produce identical output.
    """

    if session.get("status") != "completed":
        raise ValueError("Session analytics can only be built for completed sessions")
    _validate_event_scope(
        session, (engagement_events, intervention_events, assistant_events)
    )
    start, end, duration_seconds, timing_complete = _session_bounds(session)
    bounded_engagement_events = _events_within_bounds(engagement_events, start, end)
    bounded_intervention_events = _events_within_bounds(intervention_events, start, end)
    bounded_assistant_events = _events_within_bounds(assistant_events, start, end)
    timeline = segment_engagement_timeline(
        bounded_engagement_events, start, end, config=config
    )
    distribution = calculate_engagement_distribution(timeline, duration_seconds)
    recoveries = calculate_recoveries(
        bounded_intervention_events, bounded_engagement_events, end, config=config
    )
    intervention_metrics = calculate_intervention_metrics(
        bounded_intervention_events, recoveries
    )
    recovery_metrics = calculate_recovery_metrics(recoveries)
    assistant_usage = calculate_assistant_usage(bounded_assistant_events)
    critical_metrics, chunks_completed = _critical_section_metrics(
        timeline, chunk_context
    )
    data_quality = _data_quality_metrics(
        session,
        bounded_engagement_events,
        bounded_intervention_events,
        intervention_metrics,
        bounded_assistant_events,
        distribution,
        duration_seconds,
        timing_complete,
        chunk_context,
        config,
    )
    return {
        "schema_version": "1.0",
        "metric_version": config.metric_version,
        "session_id": session["session_id"],
        "user_id": session["user_id"],
        "content_id": session["content_id"],
        "duration_seconds": int(round(duration_seconds)),
        "completed_at": _format_datetime(end),
        "computed_at": _format_datetime(_parse_datetime(computed_at)),
        "engagement_distribution": distribution,
        "timeline_segments": timeline,
        "longest_focused_period": find_longest_focused_period(timeline, config),
        "intervention_metrics": intervention_metrics,
        "recovery_metrics": recovery_metrics,
        "assistant_usage": assistant_usage,
        "critical_section_engagement": critical_metrics,
        "chunks_completed": chunks_completed,
        "data_quality": data_quality,
    }

"""Contract-shaped fixtures for the Module 8 metric engine."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


BASE_TIME = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


def timestamp(offset_seconds: int) -> str:
    return (BASE_TIME + timedelta(seconds=offset_seconds)).isoformat().replace(
        "+00:00", "Z"
    )


def session(duration_seconds: int = 60) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "status": "completed",
        "started_at": timestamp(0),
        "ended_at": timestamp(duration_seconds),
        "duration_seconds": duration_seconds,
        "webcam_enabled": True,
        "voice_input_enabled": True,
        "voice_output_enabled": True,
        "intervention_count": 0,
        "assistant_message_count": 0,
    }


def engagement(
    offset_seconds: int,
    state: str,
    *,
    event_number: int,
    confidence: float = 0.9,
    chunk_id: str | None = "chunk-1",
    deep_thinking: bool = False,
    source: str = "hybrid",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": f"engagement-{event_number}",
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "chunk_id": chunk_id,
        "timestamp": timestamp(offset_seconds),
        "state": state,
        "confidence": confidence,
        "deep_thinking_detected": deep_thinking,
        "source": source,
    }


def intervention(
    offset_seconds: int,
    *,
    intervention_number: int,
    intervention_type: str = "simplify_content",
    delivery_status: str = "displayed",
    outcome: str = "not_observed",
    helped: bool | None = None,
    recovery_offset: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "schema_version": "1.0",
        "intervention_id": f"intervention-{intervention_number}",
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "chunk_id": "chunk-1",
        "timestamp": timestamp(offset_seconds),
        "intervention_type": intervention_type,
        "reason_code": "struggling",
        "reason": "A shorter explanation may make this section easier to follow.",
        "triggering_engagement_state": "struggling",
        "triggering_engagement_event_id": None,
        "delivery_status": delivery_status,
        "outcome": outcome,
        "helped": helped,
        "policy_version": "1.0",
        "model_version": None,
    }
    if recovery_offset is not None:
        item["recovery_timestamp"] = timestamp(recovery_offset)
        item["recovery_duration_seconds"] = recovery_offset - offset_seconds
    else:
        item["recovery_timestamp"] = None
        item["recovery_duration_seconds"] = None
    return item


def assistant(
    offset_seconds: int,
    *,
    event_number: int,
    direction: str,
    input_mode: str,
    response_mode: str,
    suggested_question_used: bool = False,
    status: str = "success",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": f"assistant-{event_number}",
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "chunk_id": "chunk-1",
        "timestamp": timestamp(offset_seconds),
        "direction": direction,
        "input_mode": input_mode,
        "response_mode": response_mode,
        "intent": "clarification",
        "learner_signal": "neutral",
        "suggested_question_used": suggested_question_used,
        "status": status,
        "error_code": "assistant_error" if status == "error" else None,
        "model_name": "gemini",
        "model_version": "fixture",
    }


def chunk_context() -> list[dict[str, Any]]:
    return [
        {"chunk_id": "chunk-1", "is_critical": True, "completed": True},
        {"chunk_id": "chunk-2", "is_critical": False, "completed": True},
    ]


def normal_completed_session() -> dict[str, Any]:
    events = [
        engagement(offset, state, event_number=index + 1)
        for index, (offset, state) in enumerate(
            (
                (0, "focused"),
                (5, "focused"),
                (10, "drifting"),
                (15, "struggling"),
                (20, "struggling"),
                (25, "recovered"),
                (30, "focused"),
                (35, "focused"),
                (40, "focused"),
                (45, "fatigued"),
                (50, "focused"),
                (55, "focused"),
            )
        )
    ]
    interventions = [
        intervention(
            20,
            intervention_number=1,
            outcome="recovered",
            helped=True,
            recovery_offset=25,
        )
    ]
    assistants = [
        assistant(
            12,
            event_number=1,
            direction="learner",
            input_mode="typed",
            response_mode="not_applicable",
        ),
        assistant(
            14,
            event_number=2,
            direction="assistant",
            input_mode="not_applicable",
            response_mode="text",
        ),
    ]
    session_data = session()
    session_data["intervention_count"] = len(interventions)
    session_data["assistant_message_count"] = len(assistants)
    return {
        "session": session_data,
        "engagement_events": events,
        "intervention_events": interventions,
        "assistant_events": assistants,
        "chunk_context": chunk_context(),
    }


def no_interventions() -> dict[str, Any]:
    fixture = normal_completed_session()
    fixture["intervention_events"] = []
    fixture["session"]["intervention_count"] = 0
    return fixture


def successful_recovery() -> dict[str, Any]:
    fixture = normal_completed_session()
    fixture["engagement_events"] = [
        engagement(0, "focused", event_number=1),
        engagement(5, "struggling", event_number=2),
        engagement(10, "struggling", event_number=3),
        engagement(20, "focused", event_number=4),
        engagement(25, "focused", event_number=5),
        engagement(30, "focused", event_number=6),
        engagement(35, "focused", event_number=7),
        engagement(40, "focused", event_number=8),
        engagement(45, "focused", event_number=9),
        engagement(50, "focused", event_number=10),
        engagement(55, "focused", event_number=11),
    ]
    fixture["intervention_events"] = [intervention(10, intervention_number=1)]
    return fixture


def no_observed_recovery() -> dict[str, Any]:
    fixture = normal_completed_session()
    fixture["engagement_events"] = [
        engagement(offset, "struggling", event_number=index + 1)
        for index, offset in enumerate(range(0, 60, 5))
    ]
    fixture["intervention_events"] = [intervention(10, intervention_number=1)]
    return fixture


def sparse_missing_engagement() -> dict[str, Any]:
    fixture = no_interventions()
    fixture["engagement_events"] = [
        engagement(0, "focused", event_number=1),
        engagement(50, "focused", event_number=2),
    ]
    return fixture


def paused_timing_gap() -> dict[str, Any]:
    fixture = no_interventions()
    fixture["engagement_events"] = [
        engagement(0, "focused", event_number=1),
        engagement(5, "focused", event_number=2),
        engagement(35, "focused", event_number=3),
        engagement(40, "focused", event_number=4),
        engagement(45, "focused", event_number=5),
        engagement(50, "focused", event_number=6),
        engagement(55, "focused", event_number=7),
    ]
    return fixture


def overlapping_interventions() -> dict[str, Any]:
    fixture = normal_completed_session()
    fixture["engagement_events"] = [
        engagement(0, "focused", event_number=1),
        engagement(5, "struggling", event_number=2),
        engagement(10, "struggling", event_number=3),
        engagement(15, "struggling", event_number=4),
        engagement(20, "struggling", event_number=5),
        engagement(25, "struggling", event_number=6),
        engagement(30, "focused", event_number=7),
        engagement(35, "focused", event_number=8),
        engagement(40, "focused", event_number=9),
        engagement(45, "focused", event_number=10),
        engagement(50, "focused", event_number=11),
        engagement(55, "focused", event_number=12),
    ]
    fixture["intervention_events"] = [
        intervention(10, intervention_number=1),
        intervention(
            25,
            intervention_number=2,
            intervention_type="assistant_help_prompt",
            delivery_status="accepted",
        ),
    ]
    fixture["session"]["intervention_count"] = 2
    return fixture


def deep_thinking_case() -> dict[str, Any]:
    fixture = no_interventions()
    fixture["engagement_events"] = [
        engagement(
            offset,
            "drifting",
            event_number=index + 1,
            deep_thinking=True,
        )
        for index, offset in enumerate(range(0, 60, 5))
    ]
    return fixture


def no_assistant_usage() -> dict[str, Any]:
    fixture = normal_completed_session()
    fixture["assistant_events"] = []
    fixture["session"]["assistant_message_count"] = 0
    return fixture


def voice_and_suggested_question_usage() -> dict[str, Any]:
    fixture = no_interventions()
    fixture["assistant_events"] = [
        assistant(
            5,
            event_number=1,
            direction="learner",
            input_mode="voice",
            response_mode="not_applicable",
        ),
        assistant(
            7,
            event_number=2,
            direction="assistant",
            input_mode="not_applicable",
            response_mode="voice",
        ),
        assistant(
            20,
            event_number=3,
            direction="learner",
            input_mode="suggested_question",
            response_mode="not_applicable",
            suggested_question_used=True,
        ),
        assistant(
            22,
            event_number=4,
            direction="assistant",
            input_mode="not_applicable",
            response_mode="text",
        ),
    ]
    fixture["session"]["assistant_message_count"] = 4
    return fixture


SCENARIO_FIXTURES = {
    "normal_completed_session": normal_completed_session(),
    "no_interventions": no_interventions(),
    "successful_recovery": successful_recovery(),
    "no_observed_recovery": no_observed_recovery(),
    "sparse_missing_engagement": sparse_missing_engagement(),
    "paused_timing_gap": paused_timing_gap(),
    "overlapping_interventions": overlapping_interventions(),
    "deep_thinking_case": deep_thinking_case(),
    "no_assistant_usage": no_assistant_usage(),
    "voice_and_suggested_question_usage": voice_and_suggested_question_usage(),
}


def fixture(name: str) -> dict[str, Any]:
    """Return an isolated copy so tests cannot mutate shared fixture state."""

    return deepcopy(SCENARIO_FIXTURES[name])

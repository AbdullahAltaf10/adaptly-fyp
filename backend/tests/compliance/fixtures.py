"""Minimal session-summary fragments for Module 10 score-engine tests.

Only the subsections ``backend.app.compliance.domain.score`` actually reads
are populated (``duration_seconds``, ``engagement_distribution``,
``critical_section_engagement``, ``recovery_metrics``, ``assistant_usage``,
``data_quality``). This intentionally does not reuse
``backend.tests.analytics.fixtures`` (Module 8's own event-level fixtures) --
Module 10's score engine consumes an already-computed session summary, not
raw events, so building summaries directly here keeps this test module
independent of Module 8's event-shaped fixture builders.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _distribution(
    *, focused: float = 0.0, recovered: float = 0.0, unknown: float = 0.0, other: float = 0.0
) -> dict[str, Any]:
    return {
        "focused": {"duration_seconds": focused, "percentage": 0.0},
        "drifting": {"duration_seconds": 0.0, "percentage": 0.0},
        "struggling": {"duration_seconds": 0.0, "percentage": 0.0},
        "fatigued": {"duration_seconds": other, "percentage": 0.0},
        "recovered": {"duration_seconds": recovered, "percentage": 0.0},
        "unknown": {"duration_seconds": unknown, "percentage": 0.0},
    }


def full_summary() -> dict[str, Any]:
    """Every component scorable: 80% attentional presence, 0.5 critical
    engagement, 0.5 recovery rate, 1 of 2 learner messages answered.
    """

    return {
        "duration_seconds": 100,
        "engagement_distribution": _distribution(focused=70, recovered=10, unknown=0, other=20),
        "critical_section_engagement": {
            "critical_section_count": 2,
            "engaged_section_count": 1,
            "engagement_rate": 0.5,
            "focused_duration_seconds": 30,
        },
        "recovery_metrics": {
            "eligible_intervention_count": 2,
            "recovered_intervention_count": 1,
            "recovery_rate": 0.5,
            "average_recovery_time_seconds": 12.0,
        },
        "assistant_usage": {
            "total_event_count": 4,
            "learner_message_count": 2,
            "assistant_message_count": 2,
            "typed_input_count": 2,
            "voice_input_count": 0,
            "suggested_question_count": 0,
            "text_response_count": 2,
            "voice_response_count": 0,
            "successful_interaction_count": 1,
            "error_count": 0,
        },
        "data_quality": {
            "has_sufficient_data": True,
            "event_coverage_rate": 0.9,
            "unknown_duration_seconds": 0,
            "flags": [],
        },
    }


def no_critical_sections() -> dict[str, Any]:
    summary = deepcopy(full_summary())
    summary["critical_section_engagement"] = {
        "critical_section_count": 0,
        "engaged_section_count": 0,
        "engagement_rate": None,
        "focused_duration_seconds": 0,
    }
    return summary


def no_eligible_recovery() -> dict[str, Any]:
    summary = deepcopy(full_summary())
    summary["recovery_metrics"] = {
        "eligible_intervention_count": 0,
        "recovered_intervention_count": 0,
        "recovery_rate": None,
        "average_recovery_time_seconds": None,
    }
    return summary


def no_chat_activity() -> dict[str, Any]:
    summary = deepcopy(full_summary())
    summary["assistant_usage"] = {
        "total_event_count": 0,
        "learner_message_count": 0,
        "assistant_message_count": 0,
        "typed_input_count": 0,
        "voice_input_count": 0,
        "suggested_question_count": 0,
        "text_response_count": 0,
        "voice_response_count": 0,
        "successful_interaction_count": 0,
        "error_count": 0,
    }
    return summary


def all_unknown() -> dict[str, Any]:
    """No known-state time at all: attentional_presence's denominator is 0."""

    summary = deepcopy(full_summary())
    summary["duration_seconds"] = 100
    summary["engagement_distribution"] = _distribution(unknown=100)
    return summary


def insufficient_data_flagged() -> dict[str, Any]:
    summary = deepcopy(full_summary())
    summary["data_quality"] = {
        "has_sufficient_data": False,
        "event_coverage_rate": 0.2,
        "unknown_duration_seconds": 80,
        "flags": ["sparse_engagement"],
    }
    return summary


def all_components_missing() -> dict[str, Any]:
    summary = deepcopy(no_critical_sections())
    summary = deepcopy(summary)
    summary["recovery_metrics"] = no_eligible_recovery()["recovery_metrics"]
    summary["assistant_usage"] = no_chat_activity()["assistant_usage"]
    summary["engagement_distribution"] = _distribution(unknown=100)
    return summary


def zero_score() -> dict[str, Any]:
    """Every scorable component at its floor: 0% engaged time, 0 recovery, 0 chat success."""

    summary = deepcopy(full_summary())
    summary["engagement_distribution"] = _distribution(unknown=0, other=100)
    summary["critical_section_engagement"]["engagement_rate"] = 0.0
    summary["recovery_metrics"]["recovery_rate"] = 0.0
    summary["assistant_usage"]["successful_interaction_count"] = 0
    return summary


def perfect_score() -> dict[str, Any]:
    """Every scorable component at its ceiling: 100% focused, full recovery, full chat success."""

    summary = deepcopy(full_summary())
    summary["engagement_distribution"] = _distribution(focused=100)
    summary["critical_section_engagement"]["engagement_rate"] = 1.0
    summary["recovery_metrics"]["recovery_rate"] = 1.0
    summary["assistant_usage"]["learner_message_count"] = 2
    summary["assistant_usage"]["successful_interaction_count"] = 2
    return summary

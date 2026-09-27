"""Deterministic, infrastructure-independent Module 10 Engagement Quality Score
calculation (Issue #72).

Mirrors the layering ``backend/app/analytics/domain/metrics.py`` (Module 8's
Issue #26) already established: this module accepts an ordinary mapping
shaped like ``shared/contracts/session-summary.schema.json`` and returns a
plain dict. It deliberately does not import FastAPI, MongoDB, or anything
from ``backend/app/compliance/persistence`` or ``backend/app/compliance/api``
— wiring this into storage/an endpoint is Issue #74, the same way Module 8's
metric engine (#26) didn't touch persistence (#27) or the API (#29).

Four components, each normalized to 0-1 before being expressed as an integer
0-100, combine into one Engagement Quality Score:

- ``attentional_presence`` — the share of *known* session time (session
  duration minus ``unknown`` duration) the learner spent ``focused`` or
  ``recovered``. Not applicable when there is no known-state time at all.
- ``critical_section_engagement`` — the session summary's own
  ``critical_section_engagement.engagement_rate``. Not applicable when
  ``critical_section_count`` is 0 -- this is the normal, expected state for
  every real session today, since Module 9 (which tags chunks as critical)
  does not exist yet. See CLAUDE.md (renamed to PROJECT_CONTEXT.md by PR #64)'s
  Module Map and ``metrics.py::_critical_section_metrics``, which this reads
  verbatim.
- ``recovery_rate`` — the session summary's ``recovery_metrics.recovery_rate``.
  Not applicable when that is ``null`` (no interventions were eligible for
  recovery measurement this session).
- ``chatbot_engagement`` — see the module-10 README's decisions log for the
  exact reasoning. In short: ``assistant-event.schema.json`` has no
  correlation ID pairing a learner message to its response (a documented
  Module 8 gap, CLAUDE.md (renamed to PROJECT_CONTEXT.md by PR #64) 6.6 gap
  #1), so an exact "share of chat exchanges
  answered successfully" cannot be computed. This uses
  ``successful_interaction_count / learner_message_count`` (clamped to 1.0)
  as the most conservative available proxy, and is ``not_applicable`` -- never
  0 -- when the learner sent no assistant messages at all, since no chat
  activity is neutral information, not evidence of low engagement.

Unknown/not-applicable is never silently treated as zero (CLAUDE.md (renamed
to PROJECT_CONTEXT.md by PR #64) 6.5 rule #1): a component that cannot be
computed is excluded from the score and its
weight is redistributed across the remaining components, never averaged in
as a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

SCORE_VERSION = "1.0"

COMPONENT_KEYS = (
    "attentional_presence",
    "critical_section_engagement",
    "recovery_rate",
    "chatbot_engagement",
)


@dataclass(frozen=True)
class ScoreConfig:
    """Versioned weights used by the Engagement Quality Score calculation.

    Kept separate from Module 8's ``MetricConfig``/``LearningProfileConfig``:
    this config governs a different, later calculation with its own
    reproducibility needs (``score_version``), the same separation Module 8
    already keeps between ``metric_version`` and its own config classes.
    """

    score_version: str = SCORE_VERSION
    attentional_presence_weight: float = 0.25
    critical_section_engagement_weight: float = 0.25
    recovery_rate_weight: float = 0.25
    chatbot_engagement_weight: float = 0.25

    def __post_init__(self) -> None:
        total_weight = (
            self.attentional_presence_weight
            + self.critical_section_engagement_weight
            + self.recovery_rate_weight
            + self.chatbot_engagement_weight
        )
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("Component weights must sum to 1.0")
        for weight in (
            self.attentional_presence_weight,
            self.critical_section_engagement_weight,
            self.recovery_rate_weight,
            self.chatbot_engagement_weight,
        ):
            if weight < 0:
                raise ValueError("Component weights must not be negative")


DEFAULT_CONFIG = ScoreConfig()


def _weight_for(key: str, config: ScoreConfig) -> float:
    return getattr(config, f"{key}_weight")


def _attentional_presence(summary: Mapping[str, Any]) -> tuple[float | None, str | None]:
    distribution = summary["engagement_distribution"]
    known_duration = summary["duration_seconds"] - distribution["unknown"]["duration_seconds"]
    if known_duration <= 0:
        return None, "No known-state engagement time exists to score in this session."
    engaged_duration = (
        distribution["focused"]["duration_seconds"]
        + distribution["recovered"]["duration_seconds"]
    )
    ratio = engaged_duration / known_duration
    return max(0.0, min(1.0, ratio)), None


def _critical_section_engagement(
    summary: Mapping[str, Any]
) -> tuple[float | None, str | None]:
    critical = summary["critical_section_engagement"]
    if critical["critical_section_count"] == 0:
        return None, (
            "No critical sections were tagged for this session "
            "(critical-section tagging is owned by Module 9, not yet implemented)."
        )
    rate = critical["engagement_rate"]
    if rate is None:
        return None, "Critical-section engagement rate could not be determined."
    return rate, None


def _recovery_rate(summary: Mapping[str, Any]) -> tuple[float | None, str | None]:
    rate = summary["recovery_metrics"]["recovery_rate"]
    if rate is None:
        return None, "No interventions were eligible for recovery measurement this session."
    return rate, None


def _chatbot_engagement(summary: Mapping[str, Any]) -> tuple[float | None, str | None]:
    usage = summary["assistant_usage"]
    learner_messages = usage["learner_message_count"]
    if learner_messages == 0:
        return None, "The learner sent no assistant messages during this session."
    ratio = usage["successful_interaction_count"] / learner_messages
    return min(1.0, ratio), None


_COMPONENT_FUNCTIONS: dict[str, Callable[[Mapping[str, Any]], tuple[float | None, str | None]]] = {
    "attentional_presence": _attentional_presence,
    "critical_section_engagement": _critical_section_engagement,
    "recovery_rate": _recovery_rate,
    "chatbot_engagement": _chatbot_engagement,
}


def build_engagement_quality_score(
    summary: Mapping[str, Any],
    *,
    config: ScoreConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Build the score-related portion of one compliance report.

    Returns ``score_version``, ``status``, ``engagement_quality_score``,
    ``components``, and ``excluded_components`` -- the envelope fields
    (``report_id``, ``session_id``, ``critical_sections``, ...) are assembled
    by Issue #73's report builder, which calls this function and combines its
    output with Issue #73's critical-section evidence.
    """

    components: list[dict[str, Any]] = []
    excluded_components: list[dict[str, Any]] = []
    raw_scores: dict[str, float] = {}

    for key in COMPONENT_KEYS:
        value, reason = _COMPONENT_FUNCTIONS[key](summary)
        weight = _weight_for(key, config)
        if value is None:
            components.append(
                {
                    "key": key,
                    "score": None,
                    "weight": weight,
                    "weight_applied": 0.0,
                    "status": "not_applicable",
                    "reason": reason,
                }
            )
            excluded_components.append({"key": key, "reason": reason})
        else:
            raw_scores[key] = value
            components.append(
                {
                    "key": key,
                    "score": int(round(value * 100)),
                    "weight": weight,
                    "weight_applied": 0.0,
                    "status": "included",
                    "reason": None,
                }
            )

    data_quality = summary["data_quality"]
    insufficient = not data_quality.get("has_sufficient_data", False) or not raw_scores

    if insufficient:
        return {
            "score_version": config.score_version,
            "status": "insufficient_data",
            "engagement_quality_score": None,
            "components": components,
            "excluded_components": excluded_components,
        }

    total_weight = sum(_weight_for(key, config) for key in raw_scores)
    weighted_sum = 0.0
    for component in components:
        key = component["key"]
        if component["status"] != "included":
            continue
        weight_applied = _weight_for(key, config) / total_weight
        component["weight_applied"] = round(weight_applied, 6)
        weighted_sum += raw_scores[key] * weight_applied

    score = max(0, min(100, int(round(weighted_sum * 100))))

    return {
        "score_version": config.score_version,
        "status": "complete",
        "engagement_quality_score": score,
        "components": components,
        "excluded_components": excluded_components,
    }

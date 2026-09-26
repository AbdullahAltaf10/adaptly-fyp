"""Tests for Module 8's multi-session learning-profile aggregation (Issue #33).

Every test here is pure Python: no MongoDB, no FastAPI, no persistence layer,
and no API layer — ``build_learning_profile`` only ever receives a plain list
of contract-shaped session summaries, matching the same infra-independence
``test_metrics.py`` already exercises for the single-session engine (#26).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from backend.app.analytics.domain.learning_profile import (
    DEFAULT_LEARNING_PROFILE_CONFIG,
    LearningProfileConfig,
    build_learning_profile,
)
from backend.tests.analytics.fixtures import timestamp
from backend.tests.analytics.test_metrics import assert_schema_match

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DAY = 86400


def _schema(name: str) -> dict[str, Any]:
    path = REPOSITORY_ROOT / "shared" / "contracts" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _summary(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "metric_version": "1.0",
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "duration_seconds": 1200,
        "completed_at": timestamp(1200),
        "computed_at": timestamp(1200),
        "engagement_distribution": {
            "focused": {"duration_seconds": 900, "percentage": 75.0},
            "drifting": {"duration_seconds": 120, "percentage": 10.0},
            "struggling": {"duration_seconds": 120, "percentage": 10.0},
            "fatigued": {"duration_seconds": 0, "percentage": 0.0},
            "recovered": {"duration_seconds": 60, "percentage": 5.0},
            "unknown": {"duration_seconds": 0, "percentage": 0.0},
        },
        "timeline_segments": [],
        "longest_focused_period": {
            "started_at": timestamp(0),
            "ended_at": timestamp(900),
            "duration_seconds": 900,
            "chunk_id": "chunk-1",
        },
        "intervention_metrics": {
            "total_count": 0,
            "effective_count": 0,
            "ineffective_count": 0,
            "unknown_outcome_count": 0,
            "effectiveness_rate": None,
            "by_type": [],
        },
        "recovery_metrics": {
            "eligible_intervention_count": 0,
            "recovered_intervention_count": 0,
            "recovery_rate": None,
            "average_recovery_time_seconds": None,
        },
        "assistant_usage": {
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
        },
        "critical_section_engagement": {
            "critical_section_count": 0,
            "engaged_section_count": 0,
            "engagement_rate": None,
            "focused_duration_seconds": 0,
        },
        "chunks_completed": 0,
        "data_quality": {
            "has_sufficient_data": True,
            "event_coverage_rate": 0.95,
            "unknown_duration_seconds": 0,
            "flags": [],
        },
    }
    base.update(overrides)
    return base


def _by_type(intervention_type: str, effective: int, ineffective: int, unknown: int) -> dict:
    evaluable = effective + ineffective
    return {
        "intervention_type": intervention_type,
        "total_count": effective + ineffective + unknown,
        "effective_count": effective,
        "ineffective_count": ineffective,
        "unknown_outcome_count": unknown,
        "effectiveness_rate": round(effective / evaluable, 6) if evaluable else None,
    }


class EmptyProfileTests(unittest.TestCase):
    def test_zero_sessions_matches_the_placeholder_shape(self) -> None:
        profile = build_learning_profile("user-1", [], computed_at=timestamp(0))

        self.assertEqual(profile["sessions_analyzed"], 0)
        self.assertEqual(profile["focus_trend"], "insufficient_data")
        self.assertEqual(profile["recovery_trend"], "insufficient_data")
        self.assertEqual(profile["analysis_date_range"], {"started_at": None, "ended_at": None})
        self.assertIsNone(profile["average_session_duration_seconds"])
        self.assertIsNone(profile["average_focus_percentage"])
        self.assertEqual(profile["intervention_effectiveness_by_type"], [])
        self.assertEqual(profile["recurring_difficulty_areas"], [])
        self.assertEqual(profile["effective_support_methods"], [])
        self.assertEqual(profile["data_quality"]["flags"], ["insufficient_sessions"])
        self.assertEqual(profile["assistant_usage_patterns"]["preferred_input_mode"], "unknown")

    def test_zero_sessions_matches_the_shared_contract(self) -> None:
        profile = build_learning_profile("user-1", [], computed_at=timestamp(0))
        assert_schema_match(profile, _schema("learning-profile.schema.json"))

    def test_computed_at_is_injected_not_wall_clock(self) -> None:
        profile = build_learning_profile("user-1", [], computed_at=timestamp(500))
        self.assertEqual(profile["computed_at"], timestamp(500))


class SessionCountAndDateRangeTests(unittest.TestCase):
    def test_counts_and_orders_sessions_by_completed_at(self) -> None:
        summaries = [
            _summary(session_id="session-2", completed_at=timestamp(2 * DAY)),
            _summary(session_id="session-1", completed_at=timestamp(1 * DAY)),
            _summary(session_id="session-3", completed_at=timestamp(3 * DAY)),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(4 * DAY))

        self.assertEqual(profile["sessions_analyzed"], 3)
        self.assertEqual(
            profile["analysis_date_range"],
            {"started_at": timestamp(1 * DAY), "ended_at": timestamp(3 * DAY)},
        )

    def test_result_is_identical_regardless_of_input_order(self) -> None:
        a = _summary(session_id="session-1", completed_at=timestamp(1 * DAY))
        b = _summary(session_id="session-2", completed_at=timestamp(2 * DAY))
        c = _summary(session_id="session-3", completed_at=timestamp(3 * DAY))

        forward = build_learning_profile("user-1", [a, b, c], computed_at=timestamp(4 * DAY))
        backward = build_learning_profile("user-1", [c, b, a], computed_at=timestamp(4 * DAY))

        self.assertEqual(forward, backward)


class AverageMetricsTests(unittest.TestCase):
    def test_average_session_duration_and_focus_percentage(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                duration_seconds=600,
                engagement_distribution={
                    "focused": {"duration_seconds": 300, "percentage": 50.0},
                    "drifting": {"duration_seconds": 300, "percentage": 50.0},
                    "struggling": {"duration_seconds": 0, "percentage": 0.0},
                    "fatigued": {"duration_seconds": 0, "percentage": 0.0},
                    "recovered": {"duration_seconds": 0, "percentage": 0.0},
                    "unknown": {"duration_seconds": 0, "percentage": 0.0},
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                duration_seconds=1200,
                engagement_distribution={
                    "focused": {"duration_seconds": 1200, "percentage": 100.0},
                    "drifting": {"duration_seconds": 0, "percentage": 0.0},
                    "struggling": {"duration_seconds": 0, "percentage": 0.0},
                    "fatigued": {"duration_seconds": 0, "percentage": 0.0},
                    "recovered": {"duration_seconds": 0, "percentage": 0.0},
                    "unknown": {"duration_seconds": 0, "percentage": 0.0},
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertEqual(profile["average_session_duration_seconds"], 900)
        self.assertEqual(profile["average_focus_percentage"], 75.0)


class FocusTrendTests(unittest.TestCase):
    def _profile_for_percentages(self, percentages: list[float]) -> dict:
        summaries = [
            _summary(
                session_id=f"session-{index}",
                completed_at=timestamp(index * DAY),
                engagement_distribution={
                    "focused": {"duration_seconds": 0, "percentage": percentage},
                    "drifting": {"duration_seconds": 0, "percentage": 0.0},
                    "struggling": {"duration_seconds": 0, "percentage": 0.0},
                    "fatigued": {"duration_seconds": 0, "percentage": 0.0},
                    "recovered": {"duration_seconds": 0, "percentage": 0.0},
                    "unknown": {"duration_seconds": 0, "percentage": 0.0},
                },
            )
            for index, percentage in enumerate(percentages)
        ]
        return build_learning_profile(
            "user-1", summaries, computed_at=timestamp(len(percentages) * DAY)
        )

    def test_insufficient_data_below_minimum_sessions(self) -> None:
        profile = self._profile_for_percentages([50.0, 90.0])
        self.assertEqual(profile["focus_trend"], "insufficient_data")

    def test_improving_when_second_half_is_meaningfully_higher(self) -> None:
        profile = self._profile_for_percentages([40.0, 42.0, 80.0, 82.0])
        self.assertEqual(profile["focus_trend"], "improving")

    def test_declining_when_second_half_is_meaningfully_lower(self) -> None:
        profile = self._profile_for_percentages([90.0, 88.0, 40.0, 38.0])
        self.assertEqual(profile["focus_trend"], "declining")

    def test_stable_when_difference_is_within_threshold(self) -> None:
        profile = self._profile_for_percentages([70.0, 71.0, 72.0, 73.0])
        self.assertEqual(profile["focus_trend"], "stable")

    def test_never_compares_learner_against_other_learners(self) -> None:
        # Structural guarantee: the function signature takes only one
        # user_id's own summaries, so there is no code path for cross-learner
        # comparison in the first place.
        profile = self._profile_for_percentages([50.0, 60.0, 70.0])
        self.assertNotIn("percentile", profile)
        self.assertNotIn("rank", profile)


class RecoveryTrendTests(unittest.TestCase):
    def test_insufficient_data_when_too_few_sessions_have_a_known_recovery_rate(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                recovery_metrics={
                    "eligible_intervention_count": 1,
                    "recovered_intervention_count": 1,
                    "recovery_rate": 1.0,
                    "average_recovery_time_seconds": 30,
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                recovery_metrics={
                    "eligible_intervention_count": 0,
                    "recovered_intervention_count": 0,
                    "recovery_rate": None,
                    "average_recovery_time_seconds": None,
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertEqual(profile["recovery_trend"], "insufficient_data")

    def test_improving_recovery_rate_trend(self) -> None:
        rates = [0.2, 0.25, 0.8, 0.85]
        summaries = [
            _summary(
                session_id=f"session-{index}",
                completed_at=timestamp(index * DAY),
                recovery_metrics={
                    "eligible_intervention_count": 1,
                    "recovered_intervention_count": 1,
                    "recovery_rate": rate,
                    "average_recovery_time_seconds": 30,
                },
            )
            for index, rate in enumerate(rates)
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(4 * DAY))

        self.assertEqual(profile["recovery_trend"], "improving")

    def test_sessions_with_no_interventions_are_excluded_not_treated_as_zero(self) -> None:
        # Three sessions with a real (high) recovery rate, plus several with
        # no interventions at all (null rate). If nulls were miscounted as 0,
        # this would look like a decline; excluding them correctly keeps it
        # stable/insufficient rather than fabricating a decline.
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                recovery_metrics={
                    "eligible_intervention_count": 0,
                    "recovered_intervention_count": 0,
                    "recovery_rate": None,
                    "average_recovery_time_seconds": None,
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                recovery_metrics={
                    "eligible_intervention_count": 1,
                    "recovered_intervention_count": 1,
                    "recovery_rate": 0.9,
                    "average_recovery_time_seconds": 20,
                },
            ),
            _summary(
                session_id="session-3",
                completed_at=timestamp(3 * DAY),
                recovery_metrics={
                    "eligible_intervention_count": 0,
                    "recovered_intervention_count": 0,
                    "recovery_rate": None,
                    "average_recovery_time_seconds": None,
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(4 * DAY))

        # Only one session had a real recovery rate -> insufficient_data, not
        # a fabricated trend from treating the nulls as zero.
        self.assertEqual(profile["recovery_trend"], "insufficient_data")


class InterventionEffectivenessAggregationTests(unittest.TestCase):
    def test_sums_counts_across_sessions_and_recomputes_rate_excluding_unknown(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                intervention_metrics={
                    "total_count": 2,
                    "effective_count": 1,
                    "ineffective_count": 0,
                    "unknown_outcome_count": 1,
                    "effectiveness_rate": 1.0,
                    "by_type": [_by_type("break_suggestion", 1, 0, 1)],
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                intervention_metrics={
                    "total_count": 2,
                    "effective_count": 1,
                    "ineffective_count": 1,
                    "unknown_outcome_count": 0,
                    "effectiveness_rate": 0.5,
                    "by_type": [_by_type("break_suggestion", 1, 1, 0)],
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        by_type = {
            entry["intervention_type"]: entry
            for entry in profile["intervention_effectiveness_by_type"]
        }
        break_suggestion = by_type["break_suggestion"]
        self.assertEqual(break_suggestion["total_count"], 4)
        self.assertEqual(break_suggestion["effective_count"], 2)
        self.assertEqual(break_suggestion["ineffective_count"], 1)
        self.assertEqual(break_suggestion["unknown_outcome_count"], 1)
        # 2 effective / (2 effective + 1 ineffective) = 2/3, NOT 2/4 -- the
        # unknown outcome must be excluded from the denominator (PROJECT_CONTEXT.md
        # 6.5 rule #3).
        self.assertAlmostEqual(break_suggestion["effectiveness_rate"], 2 / 3, places=5)

    def test_intervention_types_never_used_are_omitted_not_zero_filled(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                intervention_metrics={
                    "total_count": 1,
                    "effective_count": 1,
                    "ineffective_count": 0,
                    "unknown_outcome_count": 0,
                    "effectiveness_rate": 1.0,
                    "by_type": [_by_type("break_suggestion", 1, 0, 0)],
                },
            )
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        types_present = {
            entry["intervention_type"] for entry in profile["intervention_effectiveness_by_type"]
        }
        self.assertEqual(types_present, {"break_suggestion"})

    def test_all_unknown_outcomes_yields_null_rate_not_zero(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                intervention_metrics={
                    "total_count": 2,
                    "effective_count": 0,
                    "ineffective_count": 0,
                    "unknown_outcome_count": 2,
                    "effectiveness_rate": None,
                    "by_type": [_by_type("assistant_help_prompt", 0, 0, 2)],
                },
            )
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        entry = profile["intervention_effectiveness_by_type"][0]
        self.assertIsNone(entry["effectiveness_rate"])


class EffectiveSupportMethodsTests(unittest.TestCase):
    """PROJECT_CONTEXT.md 6.6 gap #4: the evidence threshold decided in this issue."""

    def _profile_with_break_suggestion(self, effective: int, ineffective: int) -> dict:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                intervention_metrics={
                    "total_count": effective + ineffective,
                    "effective_count": effective,
                    "ineffective_count": ineffective,
                    "unknown_outcome_count": 0,
                    "effectiveness_rate": None,
                    "by_type": [_by_type("break_suggestion", effective, ineffective, 0)],
                },
            )
        ]
        return build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

    def test_below_minimum_evidence_is_excluded_even_at_100_percent(self) -> None:
        # Only 2 evaluable outcomes; default threshold is 3. Must not claim
        # "effective" off two data points, however clean they look.
        profile = self._profile_with_break_suggestion(effective=2, ineffective=0)
        self.assertEqual(profile["effective_support_methods"], [])

    def test_at_minimum_evidence_and_above_rate_threshold_is_included(self) -> None:
        profile = self._profile_with_break_suggestion(effective=3, ineffective=0)
        types = [m["intervention_type"] for m in profile["effective_support_methods"]]
        self.assertIn("break_suggestion", types)

    def test_enough_evidence_but_below_rate_threshold_is_excluded(self) -> None:
        # 3 evaluable outcomes but only 1/3 effective (~33%), below the 60%
        # bar -- plenty of evidence that it does NOT reliably help.
        profile = self._profile_with_break_suggestion(effective=1, ineffective=2)
        self.assertEqual(profile["effective_support_methods"], [])

    def test_custom_config_threshold_is_respected(self) -> None:
        lenient_config = LearningProfileConfig(minimum_evidence_count_for_effective_support=1)
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                intervention_metrics={
                    "total_count": 1,
                    "effective_count": 1,
                    "ineffective_count": 0,
                    "unknown_outcome_count": 0,
                    "effectiveness_rate": 1.0,
                    "by_type": [_by_type("break_suggestion", 1, 0, 0)],
                },
            )
        ]

        profile = build_learning_profile(
            "user-1", summaries, computed_at=timestamp(2 * DAY), config=lenient_config
        )

        types = [m["intervention_type"] for m in profile["effective_support_methods"]]
        self.assertIn("break_suggestion", types)

    def test_default_config_is_unchanged_by_a_custom_instance(self) -> None:
        LearningProfileConfig(minimum_evidence_count_for_effective_support=1)
        self.assertEqual(
            DEFAULT_LEARNING_PROFILE_CONFIG.minimum_evidence_count_for_effective_support, 3
        )


class AssistantUsagePatternsTests(unittest.TestCase):
    def test_preferred_mode_when_only_one_modality_is_used(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                assistant_usage={
                    "total_event_count": 2,
                    "learner_message_count": 1,
                    "assistant_message_count": 1,
                    "typed_input_count": 1,
                    "voice_input_count": 0,
                    "suggested_question_count": 0,
                    "text_response_count": 1,
                    "voice_response_count": 0,
                    "successful_interaction_count": 1,
                    "error_count": 0,
                },
            )
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        self.assertEqual(profile["assistant_usage_patterns"]["preferred_input_mode"], "typed")
        self.assertEqual(profile["assistant_usage_patterns"]["sessions_with_assistant_use"], 1)

    def test_preferred_mode_is_mixed_when_multiple_modalities_are_used(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                assistant_usage={
                    "total_event_count": 4,
                    "learner_message_count": 2,
                    "assistant_message_count": 2,
                    "typed_input_count": 1,
                    "voice_input_count": 1,
                    "suggested_question_count": 0,
                    "text_response_count": 2,
                    "voice_response_count": 0,
                    "successful_interaction_count": 2,
                    "error_count": 0,
                },
            )
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        self.assertEqual(profile["assistant_usage_patterns"]["preferred_input_mode"], "mixed")

    def test_preferred_mode_is_unknown_with_no_assistant_use_at_all(self) -> None:
        summaries = [_summary(session_id="session-1", completed_at=timestamp(1 * DAY))]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        self.assertEqual(profile["assistant_usage_patterns"]["preferred_input_mode"], "unknown")
        self.assertEqual(profile["assistant_usage_patterns"]["sessions_with_assistant_use"], 0)

    def test_average_learner_messages_is_averaged_over_all_sessions_not_just_active_ones(
        self,
    ) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                assistant_usage={
                    "total_event_count": 2,
                    "learner_message_count": 4,
                    "assistant_message_count": 2,
                    "typed_input_count": 4,
                    "voice_input_count": 0,
                    "suggested_question_count": 0,
                    "text_response_count": 2,
                    "voice_response_count": 0,
                    "successful_interaction_count": 2,
                    "error_count": 0,
                },
            ),
            _summary(session_id="session-2", completed_at=timestamp(2 * DAY)),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertEqual(
            profile["assistant_usage_patterns"]["average_learner_messages_per_session"], 2.0
        )


class RecurringDifficultyAreasTests(unittest.TestCase):
    def _segment(self, chunk_id: str, state: str) -> dict:
        return {
            "started_at": timestamp(0),
            "ended_at": timestamp(60),
            "duration_seconds": 60,
            "state": state,
            "average_confidence": 0.8,
            "chunk_id": chunk_id,
        }

    def test_a_chunk_difficult_in_only_one_session_is_not_recurring(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                timeline_segments=[self._segment("chunk-3", "struggling")],
            )
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        self.assertEqual(profile["recurring_difficulty_areas"], [])

    def test_a_chunk_difficult_across_two_or_more_sessions_is_recurring(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                timeline_segments=[self._segment("chunk-3", "struggling")],
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                timeline_segments=[self._segment("chunk-3", "fatigued")],
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        areas = profile["recurring_difficulty_areas"]
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0]["chunk_id"], "chunk-3")
        self.assertEqual(areas[0]["session_count"], 2)
        self.assertEqual(areas[0]["occurrence_count"], 2)
        self.assertEqual(areas[0]["label"], "chunk-3")

    def test_focused_or_unknown_segments_never_count_as_difficulty(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                timeline_segments=[
                    self._segment("chunk-3", "focused"),
                    self._segment("chunk-3", "unknown"),
                ],
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                timeline_segments=[self._segment("chunk-3", "focused")],
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertEqual(profile["recurring_difficulty_areas"], [])

    def test_segments_with_no_chunk_id_are_ignored(self) -> None:
        segment_without_chunk = self._segment("chunk-3", "struggling")
        segment_without_chunk["chunk_id"] = None
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                timeline_segments=[segment_without_chunk],
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                timeline_segments=[dict(segment_without_chunk)],
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertEqual(profile["recurring_difficulty_areas"], [])


class CriticalSectionAggregatesTests(unittest.TestCase):
    def test_aggregates_only_over_sessions_with_critical_sections(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                critical_section_engagement={
                    "critical_section_count": 2,
                    "engaged_section_count": 2,
                    "engagement_rate": 1.0,
                    "focused_duration_seconds": 100,
                },
                engagement_distribution={
                    "focused": {"duration_seconds": 900, "percentage": 90.0},
                    "drifting": {"duration_seconds": 0, "percentage": 0.0},
                    "struggling": {"duration_seconds": 0, "percentage": 0.0},
                    "fatigued": {"duration_seconds": 0, "percentage": 0.0},
                    "recovered": {"duration_seconds": 0, "percentage": 0.0},
                    "unknown": {"duration_seconds": 0, "percentage": 10.0},
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                critical_section_engagement={
                    "critical_section_count": 0,
                    "engaged_section_count": 0,
                    "engagement_rate": None,
                    "focused_duration_seconds": 0,
                },
                engagement_distribution={
                    "focused": {"duration_seconds": 0, "percentage": 10.0},
                    "drifting": {"duration_seconds": 0, "percentage": 0.0},
                    "struggling": {"duration_seconds": 0, "percentage": 0.0},
                    "fatigued": {"duration_seconds": 0, "percentage": 0.0},
                    "recovered": {"duration_seconds": 0, "percentage": 0.0},
                    "unknown": {"duration_seconds": 0, "percentage": 90.0},
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        aggregates = profile["critical_section_aggregates"]
        self.assertEqual(aggregates["sections_observed"], 2)
        self.assertEqual(aggregates["sessions_with_critical_sections"], 1)
        self.assertEqual(aggregates["average_engagement_rate"], 1.0)
        # Only session-1's 90% is averaged in -- session-2 had no critical
        # sections and must not drag this figure toward its unrelated 10%.
        self.assertEqual(aggregates["average_focus_percentage"], 90.0)

    def test_no_sessions_with_critical_sections_yields_null_averages_not_zero(self) -> None:
        summaries = [_summary(session_id="session-1", completed_at=timestamp(1 * DAY))]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        aggregates = profile["critical_section_aggregates"]
        self.assertEqual(aggregates["sessions_with_critical_sections"], 0)
        self.assertIsNone(aggregates["average_engagement_rate"])
        self.assertIsNone(aggregates["average_focus_percentage"])


class DataQualityFlagsTests(unittest.TestCase):
    def test_insufficient_sessions_flag_below_minimum(self) -> None:
        summaries = [_summary(session_id="session-1", completed_at=timestamp(1 * DAY))]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(2 * DAY))

        self.assertIn("insufficient_sessions", profile["data_quality"]["flags"])

    def test_no_insufficient_sessions_flag_at_minimum(self) -> None:
        summaries = [
            _summary(session_id="session-1", completed_at=timestamp(1 * DAY)),
            _summary(session_id="session-2", completed_at=timestamp(2 * DAY)),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertNotIn("insufficient_sessions", profile["data_quality"]["flags"])

    def test_inconsistent_metric_versions_is_flagged(self) -> None:
        summaries = [
            _summary(
                session_id="session-1", completed_at=timestamp(1 * DAY), metric_version="1.0"
            ),
            _summary(
                session_id="session-2", completed_at=timestamp(2 * DAY), metric_version="1.1"
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertIn("inconsistent_metric_versions", profile["data_quality"]["flags"])
        # The profile's OWN metric_version is the current engine version --
        # separate from the versions its inputs happened to be computed
        # under (PROJECT_CONTEXT.md 6.5 rule #4).
        self.assertEqual(profile["metric_version"], "1.0")

    def test_sparse_engagement_propagates_when_a_majority_of_sessions_flagged_it(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                data_quality={
                    "has_sufficient_data": False,
                    "event_coverage_rate": 0.1,
                    "unknown_duration_seconds": 900,
                    "flags": ["sparse_engagement"],
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                data_quality={
                    "has_sufficient_data": False,
                    "event_coverage_rate": 0.2,
                    "unknown_duration_seconds": 800,
                    "flags": ["sparse_engagement"],
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertIn("sparse_engagement", profile["data_quality"]["flags"])
        self.assertEqual(profile["data_quality"]["sessions_with_sufficient_data"], 0)

    def test_sparse_engagement_not_propagated_from_a_single_outlier_session(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                data_quality={
                    "has_sufficient_data": False,
                    "event_coverage_rate": 0.1,
                    "unknown_duration_seconds": 900,
                    "flags": ["sparse_engagement"],
                },
            ),
            _summary(session_id="session-2", completed_at=timestamp(2 * DAY)),
            _summary(session_id="session-3", completed_at=timestamp(3 * DAY)),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(4 * DAY))

        self.assertNotIn("sparse_engagement", profile["data_quality"]["flags"])

    def test_insufficient_critical_section_data_when_no_session_had_any(self) -> None:
        summaries = [
            _summary(session_id="session-1", completed_at=timestamp(1 * DAY)),
            _summary(session_id="session-2", completed_at=timestamp(2 * DAY)),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertIn("insufficient_critical_section_data", profile["data_quality"]["flags"])

    def test_average_event_coverage_rate_averages_only_known_values(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                data_quality={
                    "has_sufficient_data": True,
                    "event_coverage_rate": 0.8,
                    "unknown_duration_seconds": 0,
                    "flags": [],
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                data_quality={
                    "has_sufficient_data": True,
                    "event_coverage_rate": None,
                    "unknown_duration_seconds": 0,
                    "flags": [],
                },
            ),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(3 * DAY))

        self.assertEqual(profile["data_quality"]["average_event_coverage_rate"], 0.8)


class ContractAndPrivacyTests(unittest.TestCase):
    def test_realistic_multi_session_profile_matches_the_shared_contract(self) -> None:
        summaries = [
            _summary(
                session_id="session-1",
                completed_at=timestamp(1 * DAY),
                intervention_metrics={
                    "total_count": 3,
                    "effective_count": 2,
                    "ineffective_count": 1,
                    "unknown_outcome_count": 0,
                    "effectiveness_rate": round(2 / 3, 6),
                    "by_type": [_by_type("break_suggestion", 2, 1, 0)],
                },
                recovery_metrics={
                    "eligible_intervention_count": 3,
                    "recovered_intervention_count": 2,
                    "recovery_rate": round(2 / 3, 6),
                    "average_recovery_time_seconds": 45,
                },
                critical_section_engagement={
                    "critical_section_count": 1,
                    "engaged_section_count": 1,
                    "engagement_rate": 1.0,
                    "focused_duration_seconds": 200,
                },
                timeline_segments=[self._segment("chunk-2", "struggling")],
                assistant_usage={
                    "total_event_count": 2,
                    "learner_message_count": 1,
                    "assistant_message_count": 1,
                    "typed_input_count": 1,
                    "voice_input_count": 0,
                    "suggested_question_count": 0,
                    "text_response_count": 1,
                    "voice_response_count": 0,
                    "successful_interaction_count": 1,
                    "error_count": 0,
                },
            ),
            _summary(
                session_id="session-2",
                completed_at=timestamp(2 * DAY),
                timeline_segments=[self._segment("chunk-2", "fatigued")],
            ),
            _summary(session_id="session-3", completed_at=timestamp(3 * DAY)),
        ]

        profile = build_learning_profile("user-1", summaries, computed_at=timestamp(4 * DAY))

        assert_schema_match(profile, _schema("learning-profile.schema.json"))

    @staticmethod
    def _segment(chunk_id: str, state: str) -> dict:
        return {
            "started_at": timestamp(0),
            "ended_at": timestamp(60),
            "duration_seconds": 60,
            "state": state,
            "average_confidence": 0.8,
            "chunk_id": chunk_id,
        }

    def test_module_never_references_raw_biometric_or_webcam_fields(self) -> None:
        import inspect

        from backend.app.analytics.domain import learning_profile as module

        source = inspect.getsource(module)
        for forbidden in (
            "gaze_x",
            "gaze_y",
            "head_pitch",
            "head_yaw",
            "brow_raise",
            "eye_openness",
            "blink_rate",
            "chat_history",
            "raw_prompt",
        ):
            self.assertNotIn(forbidden, source)

    def test_public_function_accepts_only_summaries_no_raw_event_parameters(self) -> None:
        import inspect

        from backend.app.analytics.domain.learning_profile import build_learning_profile

        signature = inspect.signature(build_learning_profile)
        parameter_names = set(signature.parameters)
        self.assertEqual(
            parameter_names, {"user_id", "session_summaries", "computed_at", "config"}
        )


if __name__ == "__main__":
    unittest.main()

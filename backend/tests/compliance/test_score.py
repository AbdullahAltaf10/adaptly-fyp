"""Tests for the Module 10 Engagement Quality Score engine (Issue #72)."""

from __future__ import annotations

import unittest

from backend.app.compliance.domain.score import (
    COMPONENT_KEYS,
    DEFAULT_CONFIG,
    ScoreConfig,
    build_engagement_quality_score,
)
from backend.tests.compliance import fixtures


def _component(result: dict, key: str) -> dict:
    return next(component for component in result["components"] if component["key"] == key)


class AllComponentsPresentTests(unittest.TestCase):
    def test_all_four_components_are_included_and_scored(self):
        result = build_engagement_quality_score(fixtures.full_summary())

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["excluded_components"], [])
        for key in COMPONENT_KEYS:
            component = _component(result, key)
            self.assertEqual(component["status"], "included")
            self.assertIsNone(component["reason"])
            self.assertIsInstance(component["score"], int)
            self.assertGreaterEqual(component["score"], 0)
            self.assertLessEqual(component["score"], 100)

    def test_weights_applied_sum_to_one_when_nothing_excluded(self):
        result = build_engagement_quality_score(fixtures.full_summary())
        total_weight_applied = sum(
            component["weight_applied"] for component in result["components"]
        )
        self.assertAlmostEqual(total_weight_applied, 1.0, places=6)

    def test_attentional_presence_excludes_unknown_time_from_denominator(self):
        # full_summary(): duration=100, unknown=0, focused=70, recovered=10, other(fatigued)=20.
        # known_duration = 100 - 0 = 100; engaged = 70+10 = 80 -> 80%.
        result = build_engagement_quality_score(fixtures.full_summary())
        self.assertEqual(_component(result, "attentional_presence")["score"], 80)

    def test_chatbot_engagement_is_successful_over_learner_messages(self):
        # full_summary(): 2 learner messages, 1 successful_interaction_count -> 50%.
        result = build_engagement_quality_score(fixtures.full_summary())
        self.assertEqual(_component(result, "chatbot_engagement")["score"], 50)


class IndividualComponentExclusionTests(unittest.TestCase):
    def test_no_critical_sections_excludes_that_component_not_zero(self):
        result = build_engagement_quality_score(fixtures.no_critical_sections())
        component = _component(result, "critical_section_engagement")
        self.assertEqual(component["status"], "not_applicable")
        self.assertIsNone(component["score"])
        self.assertIn("Module 9", component["reason"])
        self.assertEqual(
            {item["key"] for item in result["excluded_components"]},
            {"critical_section_engagement"},
        )
        self.assertEqual(result["status"], "complete")

    def test_no_eligible_recovery_excludes_that_component_not_zero(self):
        result = build_engagement_quality_score(fixtures.no_eligible_recovery())
        component = _component(result, "recovery_rate")
        self.assertEqual(component["status"], "not_applicable")
        self.assertIsNone(component["score"])
        self.assertEqual(result["status"], "complete")

    def test_no_chat_activity_excludes_that_component_not_zero(self):
        result = build_engagement_quality_score(fixtures.no_chat_activity())
        component = _component(result, "chatbot_engagement")
        self.assertEqual(component["status"], "not_applicable")
        self.assertIsNone(component["score"])
        self.assertIn("no assistant messages", component["reason"])
        self.assertEqual(result["status"], "complete")

    def test_no_known_state_time_excludes_attentional_presence(self):
        result = build_engagement_quality_score(fixtures.all_unknown())
        component = _component(result, "attentional_presence")
        self.assertEqual(component["status"], "not_applicable")
        self.assertIsNone(component["score"])


class InsufficientDataTests(unittest.TestCase):
    def test_all_components_missing_falls_back_to_insufficient_data(self):
        result = build_engagement_quality_score(fixtures.all_components_missing())
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["engagement_quality_score"])
        self.assertEqual(len(result["excluded_components"]), len(COMPONENT_KEYS))

    def test_data_quality_flag_forces_insufficient_data_even_with_scorable_components(self):
        result = build_engagement_quality_score(fixtures.insufficient_data_flagged())
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["engagement_quality_score"])
        # Components were still computable; this is about the aggregate score being
        # untrustworthy, not about any individual component's own applicability.
        self.assertEqual(_component(result, "attentional_presence")["status"], "included")


class ScoreBoundsAndRoundingTests(unittest.TestCase):
    def test_zero_floor(self):
        result = build_engagement_quality_score(fixtures.zero_score())
        self.assertEqual(result["engagement_quality_score"], 0)

    def test_hundred_ceiling(self):
        result = build_engagement_quality_score(fixtures.perfect_score())
        self.assertEqual(result["engagement_quality_score"], 100)

    def test_component_scores_are_rounded_to_nearest_integer(self):
        # 1/3 -> 33.33...%, rounds to 33.
        summary = fixtures.full_summary()
        summary["recovery_metrics"]["recovery_rate"] = 1 / 3
        result = build_engagement_quality_score(summary)
        self.assertEqual(_component(result, "recovery_rate")["score"], 33)


class WeightRenormalizationTests(unittest.TestCase):
    def test_excluding_one_component_renormalizes_the_rest_to_one(self):
        result = build_engagement_quality_score(fixtures.no_critical_sections())
        included = [c for c in result["components"] if c["status"] == "included"]
        self.assertEqual(len(included), 3)
        total_weight_applied = sum(c["weight_applied"] for c in included)
        self.assertAlmostEqual(total_weight_applied, 1.0, places=4)
        for component in included:
            self.assertAlmostEqual(component["weight_applied"], 1 / 3, places=6)

    def test_score_reflects_renormalized_weights_not_original_ones(self):
        # Drop critical_section_engagement (0.5) from a summary where the other three
        # components are each 100%: the excluded component must not silently count as 0
        # against the original 0.25 weight -- the score must be 100, not 75.
        summary = fixtures.perfect_score()
        summary["critical_section_engagement"] = {
            "critical_section_count": 0,
            "engaged_section_count": 0,
            "engagement_rate": None,
            "focused_duration_seconds": 0,
        }
        result = build_engagement_quality_score(summary)
        self.assertEqual(result["engagement_quality_score"], 100)


class ConfigValidationTests(unittest.TestCase):
    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            ScoreConfig(attentional_presence_weight=0.5)

    def test_default_config_weights_are_equal(self):
        self.assertEqual(DEFAULT_CONFIG.attentional_presence_weight, 0.25)
        self.assertEqual(DEFAULT_CONFIG.critical_section_engagement_weight, 0.25)
        self.assertEqual(DEFAULT_CONFIG.recovery_rate_weight, 0.25)
        self.assertEqual(DEFAULT_CONFIG.chatbot_engagement_weight, 0.25)


if __name__ == "__main__":
    unittest.main()

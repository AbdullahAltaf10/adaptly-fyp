"""
Recovery per response type — scope 6.8's "after each type of response".

The session-wide average was already there. It answers a different question:
a break and a bullet summary are not the same promise, and one number across
both describes neither. These tests pin the breakdown, and pin that adding it
did not change any number that already existed.
"""

import unittest

from app.analytics.domain.metrics import calculate_recovery_metrics


def recovery(intervention_id, recovered, duration=None):
    return {
        "intervention_id": intervention_id,
        "recovered": recovered,
        "recovery_duration_seconds": duration,
        "recovery_timestamp": "2026-09-27T10:00:00Z" if recovered else None,
    }


def intervention(intervention_id, intervention_type):
    return {"intervention_id": intervention_id, "intervention_type": intervention_type}


class SessionTotalIsUnchangedTests(unittest.TestCase):
    """The existing four numbers must mean exactly what they meant before."""

    def test_without_interventions_the_result_is_the_old_shape(self):
        results = [recovery("i1", True, 30.0), recovery("i2", False)]

        metrics = calculate_recovery_metrics(results)

        self.assertEqual(
            metrics,
            {
                "eligible_intervention_count": 2,
                "recovered_intervention_count": 1,
                "recovery_rate": 0.5,
                "average_recovery_time_seconds": 30.0,
            },
        )
        self.assertNotIn("by_type", metrics)

    def test_the_session_total_is_identical_with_and_without_the_breakdown(self):
        results = [recovery("i1", True, 30.0), recovery("i2", True, 90.0)]
        interventions = [
            intervention("i1", "bullet_summary"),
            intervention("i2", "break_suggestion"),
        ]

        without = calculate_recovery_metrics(results)
        with_breakdown = calculate_recovery_metrics(results, interventions)

        for key, value in without.items():
            self.assertEqual(with_breakdown[key], value, key)


class ByTypeTests(unittest.TestCase):
    def test_each_type_gets_its_own_average(self):
        results = [
            recovery("i1", True, 20.0),
            recovery("i2", True, 40.0),
            recovery("i3", True, 120.0),
        ]
        interventions = [
            intervention("i1", "bullet_summary"),
            intervention("i2", "bullet_summary"),
            intervention("i3", "break_suggestion"),
        ]

        by_type = calculate_recovery_metrics(results, interventions)["by_type"]

        self.assertEqual(
            by_type,
            [
                {
                    "intervention_type": "break_suggestion",
                    "eligible_intervention_count": 1,
                    "recovered_intervention_count": 1,
                    "recovery_rate": 1.0,
                    "average_recovery_time_seconds": 120.0,
                },
                {
                    "intervention_type": "bullet_summary",
                    "eligible_intervention_count": 2,
                    "recovered_intervention_count": 2,
                    "recovery_rate": 1.0,
                    "average_recovery_time_seconds": 30.0,
                },
            ],
        )

    def test_a_type_that_never_recovered_reports_that_honestly(self):
        """Null, not zero. Zero would read as "recovered instantly"."""
        results = [recovery("i1", False)]
        interventions = [intervention("i1", "break_suggestion")]

        entry = calculate_recovery_metrics(results, interventions)["by_type"][0]

        self.assertEqual(entry["recovered_intervention_count"], 0)
        self.assertEqual(entry["recovery_rate"], 0.0)
        self.assertIsNone(entry["average_recovery_time_seconds"])

    def test_types_with_no_eligible_interventions_do_not_appear(self):
        """An empty row would invite a reader to compare against nothing."""
        results = [recovery("i1", True, 10.0)]
        interventions = [
            intervention("i1", "bullet_summary"),
            intervention("i2", "simplify_content"),
        ]

        by_type = calculate_recovery_metrics(results, interventions)["by_type"]

        self.assertEqual([entry["intervention_type"] for entry in by_type], ["bullet_summary"])

    def test_a_recovery_with_no_matching_intervention_is_left_out_of_the_breakdown(self):
        """It still counts in the session total - it just has no heading."""
        results = [recovery("i1", True, 10.0), recovery("orphan", True, 50.0)]
        interventions = [intervention("i1", "bullet_summary")]

        metrics = calculate_recovery_metrics(results, interventions)

        self.assertEqual(metrics["eligible_intervention_count"], 2)
        self.assertEqual(len(metrics["by_type"]), 1)
        self.assertEqual(metrics["by_type"][0]["eligible_intervention_count"], 1)

    def test_no_recoveries_at_all_gives_an_empty_breakdown_not_an_error(self):
        metrics = calculate_recovery_metrics([], [intervention("i1", "bullet_summary")])

        self.assertEqual(metrics["by_type"], [])
        self.assertIsNone(metrics["average_recovery_time_seconds"])


class ContractTests(unittest.TestCase):
    def test_the_breakdown_matches_the_shared_contract(self):
        import json
        import os

        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        schema_path = os.path.join(
            os.path.dirname(here), "shared", "contracts", "session-summary.schema.json"
        )
        with open(schema_path, encoding="utf-8") as handle:
            schema = json.load(handle)

        recovery_schema = schema["properties"]["recovery_metrics"]
        item_schema = recovery_schema["properties"]["by_type"]["items"]

        # Optional on purpose: summaries stored before this stay valid, which
        # is why metric_version does not need a bump.
        self.assertNotIn("by_type", recovery_schema["required"])

        entry = calculate_recovery_metrics(
            [recovery("i1", True, 10.0)], [intervention("i1", "bullet_summary")]
        )["by_type"][0]
        self.assertEqual(set(entry), set(item_schema["properties"]))
        self.assertEqual(set(item_schema["required"]), set(entry))


if __name__ == "__main__":
    unittest.main()

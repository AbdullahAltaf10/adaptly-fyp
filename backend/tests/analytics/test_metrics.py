"""Unit tests for the pure Module 8 metric engine."""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.analytics.domain.metrics import (
    DEFAULT_CONFIG,
    METRIC_VERSION,
    build_session_summary,
    calculate_assistant_usage,
    calculate_engagement_distribution,
    calculate_intervention_metrics,
    calculate_recoveries,
    calculate_recovery_metrics,
    classify_intervention_effectiveness,
    find_longest_focused_period,
    MetricConfig,
    segment_engagement_timeline,
)
from backend.tests.analytics.fixtures import (
    SCENARIO_FIXTURES,
    assistant,
    engagement,
    fixture,
    intervention,
    timestamp,
)


COMPUTED_AT = "2026-08-17T10:00:00Z"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _schema_type_matches(value: Any, expected: str) -> bool:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float))
        and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return checks[expected](value)


def _resolve_local_ref(root_schema: dict, reference: str) -> dict:
    if not reference.startswith("#/"):
        raise AssertionError(f"Only local schema references are supported: {reference}")
    value: Any = root_schema
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def assert_schema_match(
    value: Any, schema: dict, root_schema: dict | None = None, path: str = "$"
) -> None:
    """Validate the JSON Schema features used by the Module 8 contracts."""

    root = root_schema or schema
    if "$ref" in schema:
        assert_schema_match(value, _resolve_local_ref(root, schema["$ref"]), root, path)
        return
    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                assert_schema_match(value, candidate, root, path)
                matches += 1
            except AssertionError:
                pass
        if matches != 1:
            raise AssertionError(f"{path}: expected exactly one oneOf match, got {matches}")
    if "const" in schema and value != schema["const"]:
        raise AssertionError(f"{path}: {value!r} does not equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise AssertionError(f"{path}: {value!r} is not in the allowed enum")

    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not any(_schema_type_matches(value, expected) for expected in expected_types):
            raise AssertionError(f"{path}: unexpected type {type(value).__name__}")

    if isinstance(value, dict) and ("properties" in schema or schema.get("type") == "object"):
        required = set(schema.get("required", ()))
        missing = required - set(value)
        if missing:
            raise AssertionError(f"{path}: missing required fields {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise AssertionError(f"{path}: unexpected fields {sorted(extra)}")
        for key, item in value.items():
            if key in properties:
                assert_schema_match(item, properties[key], root, f"{path}.{key}")

    if isinstance(value, list):
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise AssertionError(f"{path}: array items are not unique")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise AssertionError(f"{path}: fewer than minItems")
        if "items" in schema:
            for index, item in enumerate(value):
                assert_schema_match(item, schema["items"], root, f"{path}[{index}]")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise AssertionError(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise AssertionError(f"{path}: longer than maxLength")
        if schema.get("format") == "date-time":
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise AssertionError(f"{path}: date-time must include a timezone")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise AssertionError(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise AssertionError(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise AssertionError(f"{path}: not above exclusiveMinimum")

    for child_schema in schema.get("allOf", ()):
        assert_schema_match(value, child_schema, root, path)
    if "if" in schema and "then" in schema:
        try:
            assert_schema_match(value, schema["if"], root, path)
        except AssertionError:
            pass
        else:
            assert_schema_match(value, schema["then"], root, path)


def build_from_fixture(name: str) -> dict:
    values = fixture(name)
    return build_session_summary(
        values["session"],
        values["engagement_events"],
        values["intervention_events"],
        values["assistant_events"],
        computed_at=COMPUTED_AT,
        chunk_context=values["chunk_context"],
    )


class TimelineTests(unittest.TestCase):
    def test_timeline_covers_session_boundaries(self) -> None:
        values = fixture("normal_completed_session")
        timeline = segment_engagement_timeline(
            values["engagement_events"],
            values["session"]["started_at"],
            values["session"]["ended_at"],
        )
        self.assertEqual(timeline[0]["started_at"], timestamp(0))
        self.assertEqual(timeline[-1]["ended_at"], timestamp(60))
        self.assertAlmostEqual(
            sum(segment["duration_seconds"] for segment in timeline), 60.0
        )

    def test_large_gap_creates_unknown_segment(self) -> None:
        values = fixture("sparse_missing_engagement")
        timeline = segment_engagement_timeline(
            values["engagement_events"], timestamp(0), timestamp(60)
        )
        unknown = [segment for segment in timeline if segment["state"] == "unknown"]
        self.assertTrue(unknown)
        self.assertGreater(sum(item["duration_seconds"] for item in unknown), 0)

    def test_distribution_uses_all_states_and_0_to_100_percentages(self) -> None:
        values = fixture("paused_timing_gap")
        timeline = segment_engagement_timeline(
            values["engagement_events"], timestamp(0), timestamp(60)
        )
        distribution = calculate_engagement_distribution(timeline, 60)
        self.assertEqual(
            set(distribution),
            {"focused", "drifting", "struggling", "fatigued", "recovered", "unknown"},
        )
        self.assertAlmostEqual(
            sum(item["duration_seconds"] for item in distribution.values()), 60.0
        )
        self.assertAlmostEqual(
            sum(item["percentage"] for item in distribution.values()), 100.0
        )

    def test_isolated_noisy_state_does_not_break_focus(self) -> None:
        events = [
            engagement(0, "focused", event_number=1),
            engagement(5, "focused", event_number=2),
            engagement(10, "drifting", event_number=3, confidence=0.2),
            engagement(11, "focused", event_number=4),
            engagement(15, "focused", event_number=5),
            engagement(20, "focused", event_number=6),
        ]
        timeline = segment_engagement_timeline(events, timestamp(0), timestamp(25))
        longest = find_longest_focused_period(timeline)
        self.assertIsNotNone(longest)
        self.assertEqual(longest["duration_seconds"], 25.0)
        self.assertGreater(timeline[0]["average_confidence"], 0.8)

    def test_real_five_and_ten_second_nonfocused_periods_are_preserved(self) -> None:
        for state in ("struggling", "fatigued", "recovered"):
            for duration in (5, 10):
                with self.subTest(state=state, duration=duration):
                    events = [
                        engagement(0, "focused", event_number=1),
                        engagement(5, "focused", event_number=2),
                        engagement(10, state, event_number=3, confidence=0.1),
                        engagement(10 + duration, "focused", event_number=4),
                        engagement(15 + duration, "focused", event_number=5),
                    ]
                    timeline = segment_engagement_timeline(
                        events, timestamp(0), timestamp(20 + duration)
                    )
                    state_duration = sum(
                        item["duration_seconds"]
                        for item in timeline
                        if item["state"] == state
                    )
                    self.assertEqual(state_duration, float(duration))

    def test_high_confidence_short_drifting_period_is_preserved(self) -> None:
        events = [
            engagement(0, "focused", event_number=1),
            engagement(5, "drifting", event_number=2, confidence=0.9),
            engagement(6, "focused", event_number=3),
            engagement(10, "focused", event_number=4),
        ]
        timeline = segment_engagement_timeline(events, timestamp(0), timestamp(15))
        self.assertEqual(
            sum(item["duration_seconds"] for item in timeline if item["state"] == "drifting"),
            1.0,
        )

    def test_no_focused_period_returns_none(self) -> None:
        events = [
            engagement(offset, "struggling", event_number=index + 1)
            for index, offset in enumerate(range(0, 20, 5))
        ]
        timeline = segment_engagement_timeline(events, timestamp(0), timestamp(20))
        self.assertIsNone(find_longest_focused_period(timeline))

    def test_deep_thinking_counts_as_active_focus(self) -> None:
        summary = build_from_fixture("deep_thinking_case")
        self.assertEqual(
            summary["engagement_distribution"]["focused"]["percentage"], 100.0
        )
        self.assertEqual(summary["longest_focused_period"]["duration_seconds"], 60.0)

    def test_deep_thinking_does_not_override_explicit_states(self) -> None:
        for state in ("struggling", "fatigued", "recovered"):
            with self.subTest(state=state):
                events = [
                    engagement(
                        0,
                        state,
                        event_number=1,
                        deep_thinking=True,
                    ),
                    engagement(
                        5,
                        state,
                        event_number=2,
                        deep_thinking=True,
                    ),
                ]
                timeline = segment_engagement_timeline(
                    events, timestamp(0), timestamp(10)
                )
                self.assertEqual({item["state"] for item in timeline}, {state})

    def test_out_of_order_events_produce_same_timeline(self) -> None:
        events = [
            engagement(0, "focused", event_number=1),
            engagement(5, "drifting", event_number=2),
            engagement(10, "focused", event_number=3),
        ]
        ordered = segment_engagement_timeline(events, timestamp(0), timestamp(15))
        reversed_timeline = segment_engagement_timeline(
            list(reversed(events)), timestamp(0), timestamp(15)
        )
        self.assertEqual(ordered, reversed_timeline)

    def test_duplicate_ids_and_timestamps_are_deterministic(self) -> None:
        duplicate = engagement(5, "drifting", event_number=2, confidence=0.2)
        higher_confidence = engagement(5, "focused", event_number=3, confidence=0.9)
        events = [
            engagement(0, "focused", event_number=1),
            duplicate,
            dict(duplicate),
            higher_confidence,
            engagement(10, "focused", event_number=4),
        ]
        first = segment_engagement_timeline(events, timestamp(0), timestamp(15))
        second = segment_engagement_timeline(
            list(reversed(events)), timestamp(0), timestamp(15)
        )
        self.assertEqual(first, second)
        self.assertEqual({item["state"] for item in first}, {"focused"})

    def test_exact_gap_tolerance_remains_observed(self) -> None:
        events = [
            engagement(0, "focused", event_number=1),
            engagement(10, "focused", event_number=2),
        ]
        timeline = segment_engagement_timeline(events, timestamp(0), timestamp(15))
        self.assertNotIn("unknown", {item["state"] for item in timeline})


class RecoveryTests(unittest.TestCase):
    def test_successful_recovery_uses_sustained_state(self) -> None:
        values = fixture("successful_recovery")
        recoveries = calculate_recoveries(
            values["intervention_events"], values["engagement_events"], timestamp(60)
        )
        self.assertEqual(len(recoveries), 1)
        self.assertTrue(recoveries[0]["recovered"])
        self.assertEqual(recoveries[0]["recovery_timestamp"], timestamp(20))
        self.assertEqual(recoveries[0]["recovery_duration_seconds"], 10.0)

    def test_no_recovery_uses_null_not_zero(self) -> None:
        values = fixture("no_observed_recovery")
        recoveries = calculate_recoveries(
            values["intervention_events"], values["engagement_events"], timestamp(60)
        )
        self.assertFalse(recoveries[0]["recovered"])
        self.assertIsNone(recoveries[0]["recovery_timestamp"])
        self.assertIsNone(recoveries[0]["recovery_duration_seconds"])

    def test_recovery_rate_is_null_without_eligible_interventions(self) -> None:
        metrics = calculate_recovery_metrics([])
        self.assertEqual(metrics["eligible_intervention_count"], 0)
        self.assertIsNone(metrics["recovery_rate"])
        self.assertIsNone(metrics["average_recovery_time_seconds"])

    def test_recovery_rate_and_average_use_observed_recoveries(self) -> None:
        metrics = calculate_recovery_metrics(
            [
                {
                    "intervention_id": "intervention-1",
                    "recovered": True,
                    "recovery_timestamp": timestamp(20),
                    "recovery_duration_seconds": 10.0,
                },
                {
                    "intervention_id": "intervention-2",
                    "recovered": False,
                    "recovery_timestamp": None,
                    "recovery_duration_seconds": None,
                },
            ]
        )
        self.assertEqual(metrics["recovery_rate"], 0.5)
        self.assertEqual(metrics["average_recovery_time_seconds"], 10.0)

    def test_overlapping_interventions_do_not_share_recovery(self) -> None:
        values = fixture("overlapping_interventions")
        recoveries = calculate_recoveries(
            values["intervention_events"], values["engagement_events"], timestamp(60)
        )
        self.assertFalse(recoveries[0]["recovered"])
        self.assertTrue(recoveries[1]["recovered"])
        self.assertEqual(recoveries[1]["recovery_duration_seconds"], 5.0)

    def test_automatic_displayed_intervention_is_eligible(self) -> None:
        interventions = [
            intervention(
                10,
                intervention_number=1,
                intervention_type="simplify_content",
                delivery_status="displayed",
                recovery_offset=20,
            )
        ]
        recoveries = calculate_recoveries(interventions, [], timestamp(60))
        self.assertEqual(len(recoveries), 1)
        self.assertEqual(recoveries[0]["recovery_duration_seconds"], 10.0)

    def test_learner_interaction_requires_acceptance_or_completion(self) -> None:
        displayed = intervention(
            5,
            intervention_number=1,
            intervention_type="assistant_help_prompt",
            delivery_status="displayed",
        )
        accepted = intervention(
            10,
            intervention_number=2,
            intervention_type="assistant_help_prompt",
            delivery_status="accepted",
        )
        completed = intervention(
            20,
            intervention_number=3,
            intervention_type="break_suggestion",
            delivery_status="completed",
        )
        recoveries = calculate_recoveries(
            [displayed, accepted, completed], [], timestamp(60)
        )
        self.assertEqual(
            [item["intervention_id"] for item in recoveries],
            ["intervention-2", "intervention-3"],
        )

    def test_ineligible_terminal_and_pre_display_states_are_excluded(self) -> None:
        interventions = [
            intervention(
                index * 5,
                intervention_number=index,
                delivery_status=status,
            )
            for index, status in enumerate(
                ("offered", "dismissed", "failed"), start=1
            )
        ]
        self.assertEqual(calculate_recoveries(interventions, [], timestamp(60)), [])

    def test_recovery_window_boundary_is_inclusive_but_later_evidence_is_not(self) -> None:
        config = MetricConfig(recovery_window_seconds=20)
        intervention_event = intervention(0, intervention_number=1)
        at_boundary = [
            engagement(15, "focused", event_number=1),
            engagement(20, "focused", event_number=2),
        ]
        after_boundary = [
            engagement(16, "focused", event_number=3),
            engagement(21, "focused", event_number=4),
        ]
        recovered = calculate_recoveries(
            [intervention_event], at_boundary, timestamp(60), config=config
        )
        not_recovered = calculate_recoveries(
            [intervention_event], after_boundary, timestamp(60), config=config
        )
        self.assertTrue(recovered[0]["recovered"])
        self.assertFalse(not_recovered[0]["recovered"])

    def test_explicit_recovery_duration_is_derived_from_timestamps(self) -> None:
        item = intervention(
            10, intervention_number=1, recovery_offset=20
        )
        item["recovery_duration_seconds"] = 999
        recovery = calculate_recoveries([item], [], timestamp(60))[0]
        self.assertEqual(recovery["recovery_duration_seconds"], 10.0)


class InterventionTests(unittest.TestCase):
    def test_effective_intervention(self) -> None:
        item = intervention(
            10, intervention_number=1, outcome="improved", helped=True
        )
        self.assertEqual(classify_intervention_effectiveness(item), "effective")

    def test_ineffective_intervention(self) -> None:
        item = intervention(
            10, intervention_number=1, outcome="unchanged", helped=False
        )
        self.assertEqual(classify_intervention_effectiveness(item), "ineffective")

    def test_unknown_outcome_is_not_ineffective(self) -> None:
        item = intervention(10, intervention_number=1)
        self.assertEqual(classify_intervention_effectiveness(item), "unknown")

    def test_explicit_helped_value_wins_conflicting_evidence(self) -> None:
        recovery = {
            "intervention_id": "intervention-1",
            "recovered": True,
            "recovery_timestamp": timestamp(20),
            "recovery_duration_seconds": 10.0,
        }
        item = intervention(
            10,
            intervention_number=1,
            outcome="recovered",
            helped=False,
        )
        self.assertEqual(
            classify_intervention_effectiveness(item, recovery), "ineffective"
        )

    def test_effectiveness_excludes_unknown_and_groups_by_type(self) -> None:
        interventions = [
            intervention(
                5,
                intervention_number=1,
                intervention_type="simplify_content",
                helped=True,
            ),
            intervention(
                10,
                intervention_number=2,
                intervention_type="simplify_content",
                helped=False,
            ),
            intervention(
                15,
                intervention_number=3,
                intervention_type="break_suggestion",
            ),
        ]
        metrics = calculate_intervention_metrics(interventions)
        self.assertEqual(metrics["total_count"], 3)
        self.assertEqual(metrics["effective_count"], 1)
        self.assertEqual(metrics["ineffective_count"], 1)
        self.assertEqual(metrics["unknown_outcome_count"], 1)
        self.assertEqual(metrics["effectiveness_rate"], 0.5)
        simplify = next(
            item
            for item in metrics["by_type"]
            if item["intervention_type"] == "simplify_content"
        )
        self.assertEqual(simplify["effectiveness_rate"], 0.5)


class AssistantUsageTests(unittest.TestCase):
    def test_no_assistant_usage_returns_zero_counts(self) -> None:
        values = fixture("no_assistant_usage")
        usage = calculate_assistant_usage(values["assistant_events"])
        self.assertTrue(all(value == 0 for value in usage.values()))

    def test_voice_and_suggested_question_counts(self) -> None:
        values = fixture("voice_and_suggested_question_usage")
        usage = calculate_assistant_usage(values["assistant_events"])
        self.assertEqual(usage["total_event_count"], 4)
        self.assertEqual(usage["learner_message_count"], 2)
        self.assertEqual(usage["assistant_message_count"], 2)
        self.assertEqual(usage["voice_input_count"], 1)
        self.assertEqual(usage["suggested_question_count"], 1)
        self.assertEqual(usage["voice_response_count"], 1)
        self.assertEqual(usage["text_response_count"], 1)
        self.assertEqual(usage["successful_interaction_count"], 2)

    def test_success_counts_completed_assistant_responses_only(self) -> None:
        events = [
            assistant(
                5,
                event_number=1,
                direction="learner",
                input_mode="typed",
                response_mode="not_applicable",
            ),
            assistant(
                6,
                event_number=2,
                direction="assistant",
                input_mode="not_applicable",
                response_mode="text",
            ),
            assistant(
                7,
                event_number=3,
                direction="assistant",
                input_mode="not_applicable",
                response_mode="text",
                status="error",
            ),
        ]
        usage = calculate_assistant_usage(events)
        self.assertEqual(usage["successful_interaction_count"], 1)
        self.assertEqual(usage["error_count"], 1)


class SessionSummaryTests(unittest.TestCase):
    def test_empty_engagement_is_fully_unknown(self) -> None:
        values = fixture("no_interventions")
        values["engagement_events"] = []
        values["assistant_events"] = []
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertEqual(
            summary["engagement_distribution"]["unknown"]["duration_seconds"], 60.0
        )
        self.assertIn("sparse_engagement", summary["data_quality"]["flags"])
        self.assertIn("excessive_unknown_gaps", summary["data_quality"]["flags"])
        self.assertIn("no_webcam_data", summary["data_quality"]["flags"])

    def test_sparse_data_flags_and_unknown_duration(self) -> None:
        summary = build_from_fixture("sparse_missing_engagement")
        self.assertIn("sparse_engagement", summary["data_quality"]["flags"])
        self.assertIn("excessive_unknown_gaps", summary["data_quality"]["flags"])
        self.assertGreater(summary["data_quality"]["unknown_duration_seconds"], 0)

    def test_incomplete_timing_is_flagged(self) -> None:
        values = fixture("no_interventions")
        values["session"]["ended_at"] = None
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertIn("incomplete_session_timing", summary["data_quality"]["flags"])

    def test_duration_mismatch_prefers_contract_duration_and_flags_quality(self) -> None:
        values = fixture("no_interventions")
        values["session"]["duration_seconds"] = 30
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertEqual(summary["duration_seconds"], 30)
        self.assertIn("incomplete_session_timing", summary["data_quality"]["flags"])
        self.assertAlmostEqual(
            sum(
                item["duration_seconds"]
                for item in summary["engagement_distribution"].values()
            ),
            30.0,
        )

    def test_missing_chunk_context_is_flagged(self) -> None:
        values = fixture("no_interventions")
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
        )
        self.assertIn("missing_chunk_context", summary["data_quality"]["flags"])

    def test_empty_chunk_context_is_flagged(self) -> None:
        values = fixture("no_interventions")
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=[],
        )
        self.assertIn("missing_chunk_context", summary["data_quality"]["flags"])

    def test_missing_event_chunk_is_flagged_with_nonempty_context(self) -> None:
        values = fixture("normal_completed_session")
        values["assistant_events"][0]["chunk_id"] = None
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertIn("missing_chunk_context", summary["data_quality"]["flags"])

    def test_missing_intervention_outcomes_are_flagged(self) -> None:
        summary = build_from_fixture("no_observed_recovery")
        self.assertIn(
            "missing_intervention_outcomes", summary["data_quality"]["flags"]
        )

    def test_incomplete_assistant_metadata_is_flagged(self) -> None:
        values = fixture("normal_completed_session")
        values["assistant_events"][0]["response_mode"] = "text"
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertIn(
            "incomplete_assistant_metadata", summary["data_quality"]["flags"]
        )

    def test_no_webcam_evidence_is_flagged_even_when_enabled(self) -> None:
        values = fixture("no_interventions")
        for event in values["engagement_events"]:
            event["source"] = "rule"
            event["deep_thinking_detected"] = False
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertTrue(values["session"]["webcam_enabled"])
        self.assertIn("no_webcam_data", summary["data_quality"]["flags"])

    def test_no_critical_sections_uses_null_rate(self) -> None:
        values = fixture("no_interventions")
        values["chunk_context"] = [
            {"chunk_id": "chunk-1", "is_critical": False, "completed": True}
        ]
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        critical = summary["critical_section_engagement"]
        self.assertEqual(critical["critical_section_count"], 0)
        self.assertEqual(critical["engaged_section_count"], 0)
        self.assertIsNone(critical["engagement_rate"])
        self.assertEqual(critical["focused_duration_seconds"], 0.0)

    def test_positive_critical_section_metrics_and_completed_chunks(self) -> None:
        summary = build_from_fixture("normal_completed_session")
        critical = summary["critical_section_engagement"]
        self.assertEqual(critical["critical_section_count"], 1)
        self.assertEqual(critical["engaged_section_count"], 1)
        self.assertEqual(critical["engagement_rate"], 1.0)
        self.assertGreater(critical["focused_duration_seconds"], 0)
        self.assertEqual(summary["chunks_completed"], 2)

    def test_session_boundaries_are_inclusive_and_outside_events_are_ignored(self) -> None:
        values = fixture("no_interventions")
        values["session"]["ended_at"] = timestamp(20)
        values["session"]["duration_seconds"] = 20
        values["engagement_events"] = [
            engagement(-1, "struggling", event_number=90),
            engagement(0, "focused", event_number=1),
            engagement(5, "focused", event_number=2),
            engagement(10, "focused", event_number=3),
            engagement(15, "focused", event_number=4),
            engagement(20, "fatigued", event_number=5),
            engagement(21, "struggling", event_number=91),
        ]
        values["intervention_events"] = [
            intervention(-1, intervention_number=90),
            intervention(0, intervention_number=1),
            intervention(20, intervention_number=2),
            intervention(21, intervention_number=91),
        ]
        values["assistant_events"] = [
            assistant(
                -1,
                event_number=90,
                direction="assistant",
                input_mode="not_applicable",
                response_mode="text",
            ),
            assistant(
                0,
                event_number=1,
                direction="assistant",
                input_mode="not_applicable",
                response_mode="text",
            ),
            assistant(
                20,
                event_number=2,
                direction="assistant",
                input_mode="not_applicable",
                response_mode="text",
            ),
            assistant(
                21,
                event_number=91,
                direction="assistant",
                input_mode="not_applicable",
                response_mode="text",
            ),
        ]
        summary = build_session_summary(
            values["session"],
            values["engagement_events"],
            values["intervention_events"],
            values["assistant_events"],
            computed_at=COMPUTED_AT,
            chunk_context=values["chunk_context"],
        )
        self.assertEqual(summary["timeline_segments"][0]["started_at"], timestamp(0))
        self.assertEqual(summary["timeline_segments"][-1]["ended_at"], timestamp(20))
        self.assertEqual(summary["intervention_metrics"]["total_count"], 2)
        self.assertEqual(summary["assistant_usage"]["total_event_count"], 2)
        self.assertEqual(summary["assistant_usage"]["successful_interaction_count"], 2)

    def test_output_is_deterministic(self) -> None:
        first = build_from_fixture("normal_completed_session")
        second = build_from_fixture("normal_completed_session")
        self.assertEqual(first, second)

    def test_metric_version_is_centralized(self) -> None:
        summary = build_from_fixture("normal_completed_session")
        self.assertEqual(summary["metric_version"], METRIC_VERSION)
        self.assertEqual(DEFAULT_CONFIG.metric_version, METRIC_VERSION)

    def test_summary_matches_contract_top_level_shape(self) -> None:
        schema_path = (
            REPOSITORY_ROOT / "shared" / "contracts" / "session-summary.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        summary = build_from_fixture("normal_completed_session")
        self.assertEqual(set(summary), set(schema["required"]))
        self.assertTrue(set(summary).issubset(schema["properties"]))
        self.assertEqual(summary["schema_version"], "1.0")
        self.assertIsInstance(summary["duration_seconds"], int)
        self.assertEqual(summary["computed_at"], COMPUTED_AT)
        assert_schema_match(summary, schema)

    def test_every_scenario_summary_matches_nested_contract_rules(self) -> None:
        schema_path = (
            REPOSITORY_ROOT / "shared" / "contracts" / "session-summary.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for name in SCENARIO_FIXTURES:
            with self.subTest(name=name):
                assert_schema_match(build_from_fixture(name), schema)

    def test_lightweight_contract_checker_rejects_nested_range_violation(self) -> None:
        schema_path = (
            REPOSITORY_ROOT / "shared" / "contracts" / "session-summary.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        summary = build_from_fixture("normal_completed_session")
        summary["engagement_distribution"]["focused"]["percentage"] = 101
        with self.assertRaises(AssertionError):
            assert_schema_match(summary, schema)

    def test_all_event_fixtures_include_contract_required_fields(self) -> None:
        contracts = {
            "engagement_events": "engagement-event.schema.json",
            "intervention_events": "intervention-event.schema.json",
            "assistant_events": "assistant-event.schema.json",
        }
        session_schema_path = (
            REPOSITORY_ROOT / "shared" / "contracts" / "session.schema.json"
        )
        session_required = set(
            json.loads(session_schema_path.read_text(encoding="utf-8"))["required"]
        )
        session_schema = json.loads(session_schema_path.read_text(encoding="utf-8"))
        for values in SCENARIO_FIXTURES.values():
            self.assertTrue(session_required.issubset(values["session"]))
            assert_schema_match(values["session"], session_schema)
            for fixture_key, contract_name in contracts.items():
                schema_path = REPOSITORY_ROOT / "shared" / "contracts" / contract_name
                event_schema = json.loads(schema_path.read_text(encoding="utf-8"))
                required = set(event_schema["required"])
                for event in values[fixture_key]:
                    self.assertTrue(required.issubset(event))
                    assert_schema_match(event, event_schema)

    def test_non_completed_session_is_rejected(self) -> None:
        values = fixture("no_interventions")
        values["session"]["status"] = "active"
        with self.assertRaises(ValueError):
            build_session_summary(
                values["session"],
                values["engagement_events"],
                values["intervention_events"],
                values["assistant_events"],
                computed_at=COMPUTED_AT,
                chunk_context=values["chunk_context"],
            )

    def test_event_from_another_session_is_rejected(self) -> None:
        values = fixture("no_interventions")
        values["engagement_events"][0]["session_id"] = "another-session"
        with self.assertRaises(ValueError):
            build_session_summary(
                values["session"],
                values["engagement_events"],
                values["intervention_events"],
                values["assistant_events"],
                computed_at=COMPUTED_AT,
                chunk_context=values["chunk_context"],
            )


if __name__ == "__main__":
    unittest.main()

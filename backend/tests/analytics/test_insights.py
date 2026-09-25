"""Tests for Module 8's insight-report generation (Issue #32).

Every test here is pure Python: no MongoDB, no FastAPI, and no real Gemini
call — ``generate_insight_report`` always receives an injected fake
``call_gemini`` callable, per the design constraint that unit tests never hit
the network (and the free-tier 20-requests/day/model quota is never spent by
the test suite).
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from typing import Any

from backend.app.analytics.insights.fallback import build_fallback_report
from backend.app.analytics.insights.generator import generate_insight_report
from backend.app.analytics.insights.prompt import build_prompt
from backend.app.analytics.insights.validation import (
    InvalidGeminiReportError,
    validate_report_text,
)
from backend.tests.analytics.fixtures import timestamp
from backend.tests.analytics.test_metrics import assert_schema_match

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _schema(name: str) -> dict[str, Any]:
    path = REPOSITORY_ROOT / "shared" / "contracts" / name
    return json.loads(path.read_text(encoding="utf-8"))


VALID_GEMINI_TEXT = (
    "You stayed focused for most of this session, with one short dip that "
    "you recovered from after a suggested break. A summary was also offered "
    "partway through, which seemed to help you settle back into the "
    "material. Your longest focused stretch was well over ten minutes, "
    "which is a strong sign of steady attention throughout the reading. "
    "There wasn't much difficulty overall, but if you'd like to reinforce "
    "anything, it may help to revisit the section right after the short "
    "dip in focus, since that is where the break was suggested. Keep up "
    "the steady pace, and remember the assistant is available anytime you "
    "want a quick check on your understanding before moving on to the next "
    "part of the material."
)


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
            "total_count": 1,
            "effective_count": 1,
            "ineffective_count": 0,
            "unknown_outcome_count": 0,
            "effectiveness_rate": 1.0,
            "by_type": [
                {
                    "intervention_type": "break_suggestion",
                    "total_count": 1,
                    "effective_count": 1,
                    "ineffective_count": 0,
                    "unknown_outcome_count": 0,
                    "effectiveness_rate": 1.0,
                }
            ],
        },
        "recovery_metrics": {
            "eligible_intervention_count": 1,
            "recovered_intervention_count": 1,
            "recovery_rate": 1.0,
            "average_recovery_time_seconds": 60,
        },
        "assistant_usage": {
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
        "critical_section_engagement": {
            "critical_section_count": 2,
            "engaged_section_count": 2,
            "engagement_rate": 1.0,
            "focused_duration_seconds": 400,
        },
        "chunks_completed": 4,
        "data_quality": {
            "has_sufficient_data": True,
            "event_coverage_rate": 0.95,
            "unknown_duration_seconds": 60,
            "flags": [],
        },
    }
    base.update(overrides)
    return base


class PromptBuilderTests(unittest.TestCase):
    def test_prompt_includes_key_derived_numbers(self) -> None:
        prompt = build_prompt(_summary())

        self.assertIn("1200 seconds", prompt)
        self.assertIn("break_suggestion", prompt)
        self.assertIn("Duration:", prompt)

    def test_prompt_never_includes_raw_event_or_webcam_fields(self) -> None:
        summary = _summary()
        prompt = build_prompt(summary)

        for forbidden in ("gaze_x", "gaze_y", "webcam", "landmark", "chat_history"):
            self.assertNotIn(forbidden, prompt.lower())

    def test_prompt_instructs_gemini_to_stay_grounded_and_avoid_clinical_language(self) -> None:
        prompt = build_prompt(_summary())

        self.assertIn("Do not invent", prompt)
        self.assertIn("clinical", prompt.lower())

    def test_prompt_handles_missing_longest_focused_period(self) -> None:
        summary = _summary(longest_focused_period=None)
        prompt = build_prompt(summary)

        self.assertIn("could not be determined", prompt)


class FallbackReportTests(unittest.TestCase):
    def test_fallback_mentions_duration_and_support(self) -> None:
        text = build_fallback_report(_summary())

        self.assertIn("session", text.lower())
        self.assertIn("support was offered", text.lower())

    def test_fallback_never_claims_zero_recovery_when_missing(self) -> None:
        summary = _summary(
            intervention_metrics={
                "total_count": 0,
                "effective_count": 0,
                "ineffective_count": 0,
                "unknown_outcome_count": 0,
                "effectiveness_rate": None,
                "by_type": [],
            },
            recovery_metrics={
                "eligible_intervention_count": 0,
                "recovered_intervention_count": 0,
                "recovery_rate": None,
                "average_recovery_time_seconds": None,
            },
        )

        text = build_fallback_report(summary)

        self.assertIn("no extra support was offered", text.lower())
        self.assertNotIn("0%", text)

    def test_fallback_acknowledges_sparse_data_without_inventing_results(self) -> None:
        summary = _summary(
            longest_focused_period=None,
            data_quality={
                "has_sufficient_data": False,
                "event_coverage_rate": 0.1,
                "unknown_duration_seconds": 800,
                "flags": ["sparse_engagement"],
            },
        )

        text = build_fallback_report(summary)

        self.assertIn("wasn't enough engagement data", text.lower())
        self.assertNotIn("longest focused stretch lasted", text.lower())

    def test_fallback_avoids_clinical_or_judgmental_wording(self) -> None:
        text = build_fallback_report(_summary())

        for forbidden in ("failure", "poor learner", "abnormal", "deficient", "inattentive"):
            self.assertNotIn(forbidden, text.lower())

    def test_fallback_is_reasonably_close_to_the_150_word_target(self) -> None:
        text = build_fallback_report(_summary())

        word_count = len(text.split())
        self.assertGreater(word_count, 40)
        self.assertLess(word_count, 200)


class ValidationTests(unittest.TestCase):
    def test_accepts_a_well_formed_response(self) -> None:
        result = validate_report_text(VALID_GEMINI_TEXT)
        self.assertEqual(result, VALID_GEMINI_TEXT)

    def test_rejects_empty_response(self) -> None:
        with self.assertRaises(InvalidGeminiReportError):
            validate_report_text("")

    def test_rejects_none_response(self) -> None:
        with self.assertRaises(InvalidGeminiReportError):
            validate_report_text(None)

    def test_rejects_too_short_response(self) -> None:
        with self.assertRaises(InvalidGeminiReportError):
            validate_report_text("Great session!")

    def test_rejects_response_with_prohibited_clinical_wording(self) -> None:
        bad_text = VALID_GEMINI_TEXT.replace("strong sign", "sign of failure")
        with self.assertRaises(InvalidGeminiReportError):
            validate_report_text(bad_text)


class GenerateInsightReportTests(unittest.TestCase):
    def test_successful_gemini_generation_produces_a_generated_report(self) -> None:
        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: VALID_GEMINI_TEXT,
        )

        self.assertEqual(report["status"], "generated")
        self.assertEqual(report["generation_method"], "gemini")
        self.assertEqual(report["report_text"], VALID_GEMINI_TEXT)
        self.assertFalse(report["fallback_used"])
        self.assertIsNotNone(report["generated_at"])
        assert_schema_match(report, _schema("analytics-report.schema.json"))

    def test_gemini_timeout_falls_back_to_deterministic_report(self) -> None:
        def timing_out(prompt: str) -> str:
            raise TimeoutError("Gemini timed out")

        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=timing_out,
        )

        self.assertEqual(report["status"], "fallback_generated")
        self.assertEqual(report["generation_method"], "deterministic_fallback")
        self.assertTrue(report["fallback_used"])
        self.assertIsNotNone(report["report_text"])
        self.assertEqual(report["error_code"], "TimeoutError")
        assert_schema_match(report, _schema("analytics-report.schema.json"))

    def test_gemini_service_failure_falls_back_to_deterministic_report(self) -> None:
        def failing(prompt: str) -> str:
            raise RuntimeError("503 Service Unavailable")

        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=failing,
        )

        self.assertEqual(report["status"], "fallback_generated")
        self.assertTrue(report["fallback_used"])

    def test_malformed_empty_model_response_falls_back(self) -> None:
        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: "",
        )

        self.assertEqual(report["status"], "fallback_generated")
        self.assertTrue(report["fallback_used"])

    def test_missing_api_key_falls_back(self) -> None:
        from backend.app.analytics.insights.gemini_client import GeminiUnavailableError

        def no_key(prompt: str) -> str:
            raise GeminiUnavailableError("GEMINI_API_KEY is not configured.")

        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=no_key,
        )

        self.assertEqual(report["status"], "fallback_generated")
        self.assertEqual(report["error_code"], "GeminiUnavailableError")

    def test_sparse_analytics_input_still_produces_a_safe_fallback(self) -> None:
        summary = _summary(
            longest_focused_period=None,
            data_quality={
                "has_sufficient_data": False,
                "event_coverage_rate": 0.1,
                "unknown_duration_seconds": 800,
                "flags": ["sparse_engagement"],
            },
        )

        def failing(prompt: str) -> str:
            raise RuntimeError("boom")

        report = generate_insight_report(
            summary,
            session_id="session-1",
            user_id="user-1",
            call_gemini=failing,
        )

        self.assertEqual(report["status"], "fallback_generated")
        assert_schema_match(report, _schema("analytics-report.schema.json"))

    def test_unknown_intervention_outcome_is_never_claimed_as_success_by_gemini_path(
        self,
    ) -> None:
        # Gemini claiming an unknown outcome "worked" must be rejected by
        # validation and routed to the fallback instead of trusted verbatim.
        summary = _summary(
            intervention_metrics={
                "total_count": 1,
                "effective_count": 0,
                "ineffective_count": 0,
                "unknown_outcome_count": 1,
                "effectiveness_rate": None,
                "by_type": [],
            }
        )
        overclaiming_text = VALID_GEMINI_TEXT.replace(
            "which seemed to help you settle back into the material",
            "which was a total failure this time",
        )

        report = generate_insight_report(
            summary,
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: overclaiming_text,
        )

        self.assertEqual(report["status"], "fallback_generated")

    def test_retry_count_is_recorded_as_supplied_by_the_caller(self) -> None:
        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: VALID_GEMINI_TEXT,
            retry_count=2,
        )

        self.assertEqual(report["retry_count"], 2)

    def test_report_id_is_stable_across_regenerations_for_the_same_session(self) -> None:
        first = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: VALID_GEMINI_TEXT,
        )
        second = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: VALID_GEMINI_TEXT,
            retry_count=1,
        )

        self.assertEqual(first["report_id"], second["report_id"])

    def test_generated_report_matches_the_shared_contract(self) -> None:
        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=lambda prompt: VALID_GEMINI_TEXT,
        )
        assert_schema_match(report, _schema("analytics-report.schema.json"))

    def test_fallback_report_matches_the_shared_contract(self) -> None:
        def failing(prompt: str) -> str:
            raise RuntimeError("boom")

        report = generate_insight_report(
            _summary(),
            session_id="session-1",
            user_id="user-1",
            call_gemini=failing,
        )
        assert_schema_match(report, _schema("analytics-report.schema.json"))


class GeminiClientConfigTests(unittest.TestCase):
    """Covers gemini_client.py directly. Never imports google-genai: a missing
    API key is rejected before the SDK import is ever attempted, so this
    stays a pure, network-free test of configuration and guard behavior."""

    def setUp(self) -> None:
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS")
        }

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_api_key_raises_before_importing_the_sdk(self) -> None:
        from backend.app.analytics.insights.gemini_client import (
            GeminiConfig,
            GeminiUnavailableError,
            call_gemini,
        )

        config = GeminiConfig(api_key=None, model_name="gemini-2.0-flash", timeout_seconds=20)
        with self.assertRaises(GeminiUnavailableError):
            call_gemini("some prompt", config=config)

    def test_load_gemini_config_reads_environment_variables(self) -> None:
        from backend.app.analytics.insights.gemini_client import load_gemini_config

        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["GEMINI_MODEL"] = "gemini-test-model"
        os.environ["GEMINI_TIMEOUT_SECONDS"] = "5"

        config = load_gemini_config()

        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.model_name, "gemini-test-model")
        self.assertEqual(config.timeout_seconds, 5.0)

    def test_load_gemini_config_defaults_when_unset(self) -> None:
        from backend.app.analytics.insights.gemini_client import load_gemini_config

        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GEMINI_MODEL", None)
        os.environ.pop("GEMINI_TIMEOUT_SECONDS", None)

        config = load_gemini_config()

        self.assertIsNone(config.api_key)
        self.assertEqual(config.model_name, "gemini-2.0-flash")
        self.assertEqual(config.timeout_seconds, 20.0)

    def test_blank_api_key_is_treated_as_unset(self) -> None:
        from backend.app.analytics.insights.gemini_client import load_gemini_config

        os.environ["GEMINI_API_KEY"] = ""

        config = load_gemini_config()

        self.assertIsNone(config.api_key)


if __name__ == "__main__":
    unittest.main()

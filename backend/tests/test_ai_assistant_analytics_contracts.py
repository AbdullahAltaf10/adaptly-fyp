"""
Tests for backend/app/ai_assistant/analytics_contracts.py (Issue #34).

Pure function tests: no MongoDB, no FastAPI, no network. Every scenario is
also validated against the real shared/contracts/assistant-event.schema.json
via the same hand-rolled schema checker test_metrics.py already exports for
Module 8's other pure-domain tests.
"""

import json
from pathlib import Path

import pytest

from app.ai_assistant.analytics_contracts import build_assistant_events
from app.ai_assistant.schemas import AssistantMessageRequest, AssistantMessageResponse, CurrentChunk
from backend.tests.analytics.test_metrics import assert_schema_match

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _schema() -> dict:
    path = REPOSITORY_ROOT / "shared" / "contracts" / "assistant-event.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _request(question: str = "Can you explain gradient descent?") -> AssistantMessageRequest:
    return AssistantMessageRequest(
        question=question,
        session_id="session-1",
        content_id="content-1",
        current_chunk=CurrentChunk(
            chunk_id="chunk-1",
            text="Gradient descent updates model parameters to reduce error.",
            section_title="Model Training",
        ),
    )


def _response(response_mode: str = "text") -> AssistantMessageResponse:
    return AssistantMessageResponse(
        answer="Gradient descent iteratively adjusts parameters to lower error.",
        suggested_questions=[
            "Can you explain gradient descent more simply?",
            "Can you give me an example of gradient descent?",
            "Why is gradient descent important?",
        ],
        emotion_signal="neutral",
        used_context=True,
        response_mode=response_mode,
        session_id="session-1",
        content_id="content-1",
        chunk_id="chunk-1",
    )


def _assert_valid(event: dict) -> None:
    assert_schema_match(event, _schema())


class TestSuccessPath:
    def test_success_mock_mode_builds_a_correct_pair(self):
        request = _request()
        response = _response()

        learner_event, assistant_event = build_assistant_events(
            request,
            user_id="user-1",
            input_mode="typed",
            status="success",
            model_name=None,
            response=response,
        )

        assert learner_event["direction"] == "learner"
        assert assistant_event["direction"] == "assistant"
        assert learner_event["event_id"] != assistant_event["event_id"]

        assert learner_event["input_mode"] == "typed"
        assert learner_event["response_mode"] == "not_applicable"
        assert assistant_event["input_mode"] == "not_applicable"
        assert assistant_event["response_mode"] == "text"

        assert learner_event["status"] == "success"
        assert assistant_event["status"] == "success"
        assert learner_event["error_code"] is None
        assert assistant_event["error_code"] is None

        assert learner_event["model_name"] is None
        assert assistant_event["model_name"] is None

        assert learner_event["suggested_question_used"] is False
        assert assistant_event["suggested_question_used"] is False
        assert learner_event["intent"] == "unknown"
        assert assistant_event["intent"] == "unknown"

        for event in (learner_event, assistant_event):
            assert event["session_id"] == "session-1"
            assert event["user_id"] == "user-1"
            assert event["content_id"] == "content-1"
            assert event["chunk_id"] == "chunk-1"

        _assert_valid(learner_event)
        _assert_valid(assistant_event)

    def test_success_gemini_mode_sets_model_name_on_assistant_event_only(self):
        request = _request()
        response = _response()

        learner_event, assistant_event = build_assistant_events(
            request,
            user_id="user-1",
            input_mode="typed",
            status="success",
            model_name="gemini-3.6-flash",
            response=response,
        )

        assert learner_event["model_name"] is None
        assert assistant_event["model_name"] == "gemini-3.6-flash"
        assert learner_event["model_version"] is None
        assert assistant_event["model_version"] is None

        _assert_valid(learner_event)
        _assert_valid(assistant_event)


class TestFailurePath:
    @pytest.mark.parametrize(
        "error_code",
        [
            "AssistantConfigurationError",
            "AssistantProviderError",
            "AssistantProviderTimeoutError",
        ],
    )
    def test_each_exception_type_marks_the_assistant_event_as_error(self, error_code):
        request = _request()

        learner_event, assistant_event = build_assistant_events(
            request,
            user_id="user-1",
            input_mode="typed",
            status="error",
            error_code=error_code,
            model_name=None,
            response=None,
        )

        # The learner's message was still received fine; only the response failed.
        assert learner_event["status"] == "success"
        assert learner_event["error_code"] is None

        assert assistant_event["status"] == "error"
        assert assistant_event["error_code"] == error_code
        assert assistant_event["response_mode"] == "not_applicable"

        _assert_valid(learner_event)
        _assert_valid(assistant_event)

    def test_gemini_mode_failure_can_still_carry_the_attempted_model_name(self):
        request = _request()

        learner_event, assistant_event = build_assistant_events(
            request,
            user_id="user-1",
            input_mode="typed",
            status="error",
            error_code="AssistantProviderTimeoutError",
            model_name="gemini-3.6-flash",
            response=None,
        )

        assert assistant_event["model_name"] == "gemini-3.6-flash"
        _assert_valid(learner_event)
        _assert_valid(assistant_event)


class TestInvalidCombination:
    def test_success_status_without_a_response_is_rejected(self):
        with pytest.raises(ValueError):
            build_assistant_events(
                _request(),
                user_id="user-1",
                input_mode="typed",
                status="success",
                response=None,
            )

    def test_error_status_with_a_response_is_rejected(self):
        with pytest.raises(ValueError):
            build_assistant_events(
                _request(),
                user_id="user-1",
                input_mode="typed",
                status="error",
                response=_response(),
            )


class TestInputMode:
    @pytest.mark.parametrize("input_mode", ["typed", "voice", "suggested_question"])
    def test_input_mode_propagates_and_derives_suggested_question_used(self, input_mode):
        learner_event, assistant_event = build_assistant_events(
            _request(),
            user_id="user-1",
            input_mode=input_mode,
            status="success",
            response=_response(),
        )

        assert learner_event["input_mode"] == input_mode
        assert assistant_event["input_mode"] == "not_applicable"

        expected_used = input_mode == "suggested_question"
        assert learner_event["suggested_question_used"] is expected_used
        assert assistant_event["suggested_question_used"] is expected_used

        _assert_valid(learner_event)
        _assert_valid(assistant_event)


class TestLearnerSignal:
    @pytest.mark.parametrize(
        ("question", "expected_signal"),
        [
            ("Can you explain gradient descent?", "neutral"),
            ("I don't understand this at all", "confusion"),
            ("This is so frustrating, I've tried everything", "frustration"),
        ],
    )
    def test_learner_signal_is_classified_from_the_question_and_mirrored(
        self, question, expected_signal
    ):
        request = _request(question=question)

        learner_event, assistant_event = build_assistant_events(
            request,
            user_id="user-1",
            input_mode="typed",
            status="success",
            response=_response(),
        )

        assert learner_event["learner_signal"] == expected_signal
        assert assistant_event["learner_signal"] == expected_signal

        _assert_valid(learner_event)
        _assert_valid(assistant_event)

    def test_learner_signal_is_available_even_when_the_provider_call_failed(self):
        request = _request(question="I don't understand this at all")

        learner_event, assistant_event = build_assistant_events(
            request,
            user_id="user-1",
            input_mode="typed",
            status="error",
            error_code="AssistantProviderError",
            response=None,
        )

        assert learner_event["learner_signal"] == "confusion"
        assert assistant_event["learner_signal"] == "confusion"

        _assert_valid(learner_event)
        _assert_valid(assistant_event)

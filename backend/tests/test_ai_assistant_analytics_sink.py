"""
Tests for backend/app/ai_assistant/analytics_sink.py.

`record_assistant_exchange` bridges Module 5's assistant events into Module
8's analytics (`AssistantEventRepository`). These tests exercise the function
in isolation - no HTTP layer, no database, no model load - the same pattern
`test_engagement_analytics_sink.py` uses for Module 3's equivalent sink.

The core contract under test: an unreachable database must never raise out of
`record_assistant_exchange`. Module 5's `/assistant/messages` is a
learner-facing request/response endpoint, and a database hiccup must not
turn a successful answer into a failed request.
"""

import logging
from unittest.mock import patch

from app.ai_assistant.analytics_sink import record_assistant_exchange


def _events(learner_event_id="learner-event-1", assistant_event_id="assistant-event-1"):
    learner_event = {
        "schema_version": "1.0",
        "event_id": learner_event_id,
        "session_id": "session-1",
        "user_id": "user-1",
        "content_id": "content-1",
        "chunk_id": "chunk-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "direction": "learner",
        "input_mode": "typed",
        "response_mode": "not_applicable",
        "intent": "unknown",
        "learner_signal": "neutral",
        "suggested_question_used": False,
        "status": "success",
        "error_code": None,
        "model_name": None,
        "model_version": None,
    }
    assistant_event = {
        **learner_event,
        "event_id": assistant_event_id,
        "direction": "assistant",
        "input_mode": "not_applicable",
        "response_mode": "text",
    }
    return learner_event, assistant_event


def test_successful_write_returns_true_and_calls_insert_events():
    learner_event, assistant_event = _events()

    with patch("app.ai_assistant.analytics_sink.AssistantEventRepository") as repo_cls:
        result = record_assistant_exchange(learner_event, assistant_event)

    assert result is True
    repo_cls.return_value.insert_events.assert_called_once_with([learner_event, assistant_event])


def test_repository_exception_is_caught_and_returns_false():
    learner_event, assistant_event = _events()

    with patch("app.ai_assistant.analytics_sink.AssistantEventRepository") as repo_cls:
        repo_cls.return_value.insert_events.side_effect = Exception("boom")
        result = record_assistant_exchange(learner_event, assistant_event)  # must not raise

    assert result is False


def test_failure_is_logged(caplog):
    learner_event, assistant_event = _events(
        learner_event_id="learner-event-42", assistant_event_id="assistant-event-99"
    )

    with caplog.at_level(logging.WARNING, logger="app.ai_assistant.analytics_sink"):
        with patch("app.ai_assistant.analytics_sink.AssistantEventRepository") as repo_cls:
            repo_cls.return_value.insert_events.side_effect = Exception("boom")
            record_assistant_exchange(learner_event, assistant_event)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    assert "learner-event-42" in message
    assert "assistant-event-99" in message

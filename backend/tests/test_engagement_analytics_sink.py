"""
Tests for backend/app/engagement/analytics_sink.py.

`record_engagement_event` bridges Module 3's engagement events into Module 8's
analytics (`EngagementEventRepository`). These tests exercise the function in
isolation - no HTTP layer, no database, no model load - the same reasoning
`test_engagement_confidence.py` gives for testing `contracts.confidence_for`
directly rather than through the endpoint.

The core contract under test: an unreachable database must never raise out of
`record_engagement_event`. Module 3's `/analyze` endpoint is on the hot path
for every 10-frame window, and a database hiccup must not take engagement
detection down with it - the same resilience rule `intervention/store.py`
documents, and enforces, for the identical reason.
"""

import logging
from unittest.mock import patch

from app.engagement.analytics_sink import record_engagement_event


def _event(event_id="event-1"):
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "session_id": "session-1",
        "user_id": "user-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "state": "focused",
        "confidence": 0.9,
        "source": "lstm",
    }


def test_successful_write_returns_true_and_calls_insert_events():
    event = _event()

    with patch("app.engagement.analytics_sink.EngagementEventRepository") as repo_cls:
        result = record_engagement_event(event)

    assert result is True
    repo_cls.return_value.insert_events.assert_called_once_with([event])


def test_repository_exception_is_caught_and_returns_false():
    event = _event()

    with patch("app.engagement.analytics_sink.EngagementEventRepository") as repo_cls:
        repo_cls.return_value.insert_events.side_effect = Exception("boom")
        result = record_engagement_event(event)  # must not raise

    assert result is False


def test_failure_is_logged(caplog):
    event = _event(event_id="event-42")

    with caplog.at_level(logging.WARNING, logger="app.engagement.analytics_sink"):
        with patch("app.engagement.analytics_sink.EngagementEventRepository") as repo_cls:
            repo_cls.return_value.insert_events.side_effect = Exception("boom")
            record_engagement_event(event)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert "event-42" in record.getMessage()

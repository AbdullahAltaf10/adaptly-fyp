import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion.signals import FusionSignals  # noqa: E402
from app.intervention.decider import Signals  # noqa: E402


def _engagement_signals() -> Signals:
    return Signals(
        state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
        uid="u1", session_id="s1",
    )


def test_constructs_with_all_fields():
    fs = FusionSignals(
        engagement=_engagement_signals(),
        recent_emotion_signals=["confusion", "neutral"],
        assistant_message_count_last_60s=2,
        recovery_since_last_decision=False,
    )
    assert fs.engagement.state == "struggling"
    assert fs.recent_emotion_signals == ["confusion", "neutral"]
    assert fs.assistant_message_count_last_60s == 2
    assert fs.recovery_since_last_decision is False


def test_recovery_since_last_decision_accepts_none():
    """None is a real, valid third state - distinct from True/False - for
    'there was no prior decision to measure recovery from yet'."""
    fs = FusionSignals(
        engagement=_engagement_signals(),
        recent_emotion_signals=[],
        assistant_message_count_last_60s=0,
        recovery_since_last_decision=None,
    )
    assert fs.recovery_since_last_decision is None


def test_is_frozen():
    fs = FusionSignals(
        engagement=_engagement_signals(),
        recent_emotion_signals=[],
        assistant_message_count_last_60s=0,
        recovery_since_last_decision=None,
    )
    try:
        fs.assistant_message_count_last_60s = 5
        assert False, "FusionSignals must be immutable, like Signals and Decision"
    except AttributeError:
        pass


from datetime import datetime, timedelta, timezone  # noqa: E402

import mongomock  # noqa: E402

from app.fusion.signals import build_fusion_signals  # noqa: E402


def _database():
    return mongomock.MongoClient()["adaptly_test_fusion"]


def _learner_event(event_id: str, offset_seconds: int, learner_signal: str, now: datetime, *, direction: str = "learner"):
    return {
        "event_id": event_id,
        "session_id": "s1",
        "direction": direction,
        "learner_signal": learner_signal,
        "timestamp": (now - timedelta(seconds=offset_seconds)).isoformat().replace("+00:00", "Z"),
    }


def test_build_fusion_signals_with_no_assistant_exchanges():
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=_database(),
    )
    assert fs.recent_emotion_signals == []
    assert fs.assistant_message_count_last_60s == 0


def test_build_fusion_signals_counts_only_learner_direction_within_the_60s_window():
    """assistant_message_count_last_60s is strictly the last 60s (the
    FusionWindow cadence) - deliberately a SHORTER, separate window than
    recent_emotion_signals' own lookback (see the decoupling tests below:
    these two were a single window in the first cut, which made the chat
    corroboration rule unreachable - any turn that counted toward
    "confused/frustrated x2" also always counted as "already asked",
    so FusionPolicy._chat_only_decision could never fire)."""
    from app.analytics.persistence.events import AssistantEventRepository

    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    db = _database()
    AssistantEventRepository(db).insert_events([
        _learner_event("e1", 10, "confusion", now),
        _learner_event("e2", 15, "neutral", now, direction="assistant"),  # not a learner turn
    ])
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=db,
    )
    assert fs.assistant_message_count_last_60s == 1


def test_build_fusion_signals_orders_emotion_signals_oldest_to_most_recent():
    from app.analytics.persistence.events import AssistantEventRepository

    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    db = _database()
    AssistantEventRepository(db).insert_events([
        _learner_event("e1", 5, "frustration", now),
        _learner_event("e2", 45, "confusion", now),
    ])
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=True,
        now=now,
        db=db,
    )
    assert fs.recent_emotion_signals == ["confusion", "frustration"]
    assert fs.recovery_since_last_decision is True


def test_emotion_lookback_is_longer_than_and_independent_of_the_60s_message_count_window():
    """The bug this pins: two confused turns from 90s ago (outside the 60s
    message-count window, but within the longer emotion lookback) must still
    show up in recent_emotion_signals, while assistant_message_count_last_60s
    stays 0 - "sustained confusion over the recent past" and "already asked
    for help in THIS decision window" are different questions, and conflating
    them (one shared window for both) made the corroboration rule dead code:
    confirming >=2 emotion signals always also meant assistant_message_count
    was >=2 (same events), so "already asked" was always true whenever
    "corroborated" was true."""
    from app.analytics.persistence.events import AssistantEventRepository

    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    db = _database()
    AssistantEventRepository(db).insert_events([
        _learner_event("e1", 90, "confusion", now),
        _learner_event("e2", 80, "confusion", now),
    ])
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=db,
    )
    assert fs.recent_emotion_signals == ["confusion", "confusion"]
    assert fs.assistant_message_count_last_60s == 0


def test_emotion_lookback_has_its_own_bound_too():
    from app.analytics.persistence.events import AssistantEventRepository

    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    db = _database()
    AssistantEventRepository(db).insert_events([
        _learner_event("e1", 301, "confusion", now),  # just outside the default 300s lookback
    ])
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=db,
    )
    assert fs.recent_emotion_signals == []


def test_build_fusion_signals_never_raises_when_the_repository_fails():
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    class _BrokenCollection:
        def find(self, *args, **kwargs):
            raise RuntimeError("db down")

    class _BrokenDb:
        def __getitem__(self, _name):
            return _BrokenCollection()

    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=_BrokenDb(),
    )
    assert fs.recent_emotion_signals == []
    assert fs.assistant_message_count_last_60s == 0

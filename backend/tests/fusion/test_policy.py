import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion.policy import FusionPolicy  # noqa: E402
from app.intervention.decider import (  # noqa: E402
    ASSISTANT_HELP_PROMPT,
    BULLET_SUMMARY,
    REASON_FATIGUE,
    SIMPLIFY_CONTENT,
    Signals,
)


def _signals(**overrides) -> Signals:
    base = dict(
        state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=True,
        dwell_seconds=50.0, uid="u1", session_id="s1",
    )
    base.update(overrides)
    return Signals(**base)


class _StubBuildFusionSignals:
    """Replaces app.fusion.policy.build_fusion_signals for these tests, so
    they control chat signals directly without a fake database."""

    def __init__(self, recent_emotion_signals, assistant_message_count_last_60s):
        self.recent_emotion_signals = recent_emotion_signals
        self.assistant_message_count_last_60s = assistant_message_count_last_60s

    def __call__(self, engagement_signals, *, recovery_since_last_decision, **kwargs):
        from app.fusion.signals import FusionSignals

        return FusionSignals(
            engagement=engagement_signals,
            recent_emotion_signals=self.recent_emotion_signals,
            assistant_message_count_last_60s=self.assistant_message_count_last_60s,
            recovery_since_last_decision=recovery_since_last_decision,
        )


def test_defers_to_the_base_decision_when_the_window_is_not_ready(monkeypatch):
    policy = FusionPolicy()
    monkeypatch.setattr("app.fusion.policy.build_fusion_signals", _StubBuildFusionSignals([], 0))
    # First call opens the window (marks decided); the base decider would
    # say simplify_content given strong+long dwell, but the SECOND call,
    # inside the 60s window, must stay quiet regardless.
    first = policy.decide(_signals(), history=[], recovery=None)
    assert first is not None
    second = policy.decide(_signals(), history=[], recovery=None)
    assert second is None


def test_fatigue_bypasses_the_60s_window(monkeypatch):
    policy = FusionPolicy()
    monkeypatch.setattr("app.fusion.policy.build_fusion_signals", _StubBuildFusionSignals([], 0))
    policy.decide(_signals(state="fatigued"), history=[], recovery=None)
    second = policy.decide(_signals(state="fatigued"), history=[], recovery=None)
    assert second is not None
    assert second.reason_code == REASON_FATIGUE


def test_camera_decision_is_never_overridden_by_chat_when_camera_already_decided(monkeypatch):
    """The spec's central safety rule: chat can never change intervention
    TYPE when the camera signal already produced a decision - only ever
    participates in sequencing."""
    policy = FusionPolicy()
    monkeypatch.setattr(
        "app.fusion.policy.build_fusion_signals",
        _StubBuildFusionSignals(["frustration", "frustration"], 0),
    )
    result = policy.decide(_signals(), history=[], recovery=None)
    assert result is not None
    assert result.intervention_type == SIMPLIFY_CONTENT  # exactly what DefaultPolicy alone would choose


def test_chat_only_triggers_when_camera_is_silent_and_corroborated(monkeypatch):
    policy = FusionPolicy()
    monkeypatch.setattr(
        "app.fusion.policy.build_fusion_signals",
        _StubBuildFusionSignals(["confusion", "confusion"], 0),
    )
    # raw_struggling/brow_struggling both False -> DefaultPolicy alone says None
    quiet_signals = _signals(raw_struggling=False, brow_struggling=False, dwell_seconds=0.0)
    result = policy.decide(quiet_signals, history=[], recovery=None)
    assert result is not None
    assert result.intervention_type == ASSISTANT_HELP_PROMPT


def test_chat_does_not_trigger_when_the_learner_already_asked_for_help(monkeypatch):
    """Scope's own framing only holds when the learner has NOT already used
    the normal help-seeking route - if they have, there is nothing this
    signal adds."""
    policy = FusionPolicy()
    monkeypatch.setattr(
        "app.fusion.policy.build_fusion_signals",
        _StubBuildFusionSignals(["confusion", "confusion"], 1),
    )
    quiet_signals = _signals(raw_struggling=False, brow_struggling=False, dwell_seconds=0.0)
    result = policy.decide(quiet_signals, history=[], recovery=None)
    assert result is None


def test_chat_does_not_trigger_on_a_single_confused_turn(monkeypatch):
    """The threshold is >=2 of the recent turns - one is not "sustained"."""
    policy = FusionPolicy()
    monkeypatch.setattr(
        "app.fusion.policy.build_fusion_signals",
        _StubBuildFusionSignals(["confusion", "neutral"], 0),
    )
    quiet_signals = _signals(raw_struggling=False, brow_struggling=False, dwell_seconds=0.0)
    result = policy.decide(quiet_signals, history=[], recovery=None)
    assert result is None


def test_recovered_state_stays_quiet_like_default_policy(monkeypatch):
    policy = FusionPolicy()
    monkeypatch.setattr("app.fusion.policy.build_fusion_signals", _StubBuildFusionSignals([], 0))
    result = policy.decide(_signals(state="recovered"), history=[], recovery=None)
    assert result is None


def test_escalates_through_sequencing_when_the_same_type_would_repeat(monkeypatch):
    policy = FusionPolicy()
    monkeypatch.setattr("app.fusion.policy.build_fusion_signals", _StubBuildFusionSignals([], 0))
    quiet_signals = _signals(raw_struggling=False, brow_struggling=True, dwell_seconds=0.0)  # -> assistant_help_prompt via DefaultPolicy's broad tier
    history = [{
        "intervention_type": ASSISTANT_HELP_PROMPT, "sequence_id": "seq-1", "step_index": 0,
    }]
    result = policy.decide(quiet_signals, history=history, recovery=False)
    assert result is not None
    assert result.intervention_type == BULLET_SUMMARY
    assert result.sequence_id == "seq-1"
    assert result.step_index == 1


def test_a_quiet_decision_does_not_consume_the_60s_window(monkeypatch):
    """Only a REAL decision should start the 60s cadence. Marking the window
    on a None outcome would mean a single quiet frame silences
    reconsideration for the next ~59 seconds even while the learner starts
    struggling moments later - the 120s post-intervention cooldown
    (service.py) already covers "don't re-fire too soon" for actual
    interventions. FusionWindow's job is "once per 60s per actual
    decision", not "once per 60s per call"."""
    policy = FusionPolicy()
    monkeypatch.setattr("app.fusion.policy.build_fusion_signals", _StubBuildFusionSignals([], 0))
    quiet_signals = _signals(raw_struggling=False, brow_struggling=False, dwell_seconds=0.0)
    first = policy.decide(quiet_signals, history=[], recovery=None)
    assert first is None

    result = policy.decide(_signals(), history=[], recovery=None)
    assert result is not None


def test_policy_version_is_set():
    assert FusionPolicy().policy_version == "v1-fusion"


def test_chat_only_trigger_is_reachable_end_to_end_against_real_build_fusion_signals():
    """The other chat-only tests above stub build_fusion_signals entirely,
    which caught the DECISION logic but not whether real chat data could
    ever actually produce that combination. It could not: the first cut of
    build_fusion_signals used ONE window for both recent_emotion_signals and
    assistant_message_count_last_60s, so >=2 confused/frustrated turns
    always also meant assistant_message_count_last_60s >= 2, making
    "corroborated AND not already asked" impossible in production even
    though the stubbed unit tests above all passed. This test goes through
    the real build_fusion_signals (mongomock, no stubbing, no monkeypatched
    collaborators) to prove the fixed, decoupled windows actually let this
    path fire, then feeds the result through FusionPolicy's own decision
    helper exactly as policy.decide() does internally."""
    import mongomock
    from datetime import datetime, timedelta, timezone

    from app.analytics.persistence.events import AssistantEventRepository
    from app.fusion.signals import build_fusion_signals

    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    db = mongomock.MongoClient()["adaptly_test_fusion_policy"]
    AssistantEventRepository(db).insert_events([
        {
            "event_id": "e1", "session_id": "s1", "direction": "learner",
            "learner_signal": "confusion",
            "timestamp": (now - timedelta(seconds=90)).isoformat().replace("+00:00", "Z"),
        },
        {
            "event_id": "e2", "session_id": "s1", "direction": "learner",
            "learner_signal": "confusion",
            "timestamp": (now - timedelta(seconds=80)).isoformat().replace("+00:00", "Z"),
        },
    ])

    quiet_signals = _signals(raw_struggling=False, brow_struggling=False, dwell_seconds=0.0)
    fusion_signals = build_fusion_signals(
        quiet_signals, recovery_since_last_decision=None, now=now, db=db,
    )
    assert fusion_signals.recent_emotion_signals == ["confusion", "confusion"]
    assert fusion_signals.assistant_message_count_last_60s == 0

    decision = FusionPolicy._chat_only_decision(fusion_signals)
    assert decision is not None
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT

"""
FusionSignals - everything FusionPolicy is allowed to see, beyond what
Signals (Module 3/4) already carries.

Kept as its own dataclass rather than adding fields onto Signals directly:
Signals is the agreed surface between Module 3/9 and ANY decider (scope 6.4's
DefaultPolicy included), and most of what FusionSignals adds (chat history,
assistant message counts) only makes sense to a fusion-aware decider.
Bundling it in would force DefaultPolicy to carry fields it never reads.
"""

from dataclasses import dataclass

from app.intervention.decider import Signals


@dataclass(frozen=True)
class FusionSignals:
    engagement: Signals
    # Most recent last. Values are classify_conversational_signal's own
    # output shape: "frustration" | "confusion" | "neutral". Drawn from a
    # longer lookback than assistant_message_count_last_60s (see
    # build_fusion_signals) - this is "has the learner been showing
    # distress recently", not "right in this exact 60s decision window".
    recent_emotion_signals: list[str]
    # "Did the learner ask for help through the panel, in THIS 60s decision
    # window specifically?" - deliberately a shorter, separate window than
    # recent_emotion_signals' lookback. Sharing one window for both made the
    # chat corroboration rule unreachable: any turn that counted toward
    # ">=2 confused/frustrated" necessarily also counted toward this field,
    # so "corroborated AND not already asked" could never both be true.
    assistant_message_count_last_60s: int
    # None means "no prior decision this session to measure recovery from
    # yet" - distinct from False ("measured, and no recovery observed").
    recovery_since_last_decision: bool | None


import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def build_fusion_signals(
    engagement_signals: Signals,
    *,
    recovery_since_last_decision: bool | None,
    now: datetime | None = None,
    window_seconds: float = 60.0,
    emotion_lookback_seconds: float = 300.0,
    db=None,
) -> "FusionSignals":
    """Read this session's recent assistant-chat history and combine it
    with the already-computed camera signals and recovery state.

    Two deliberately different windows, read from the same event list:
    `emotion_lookback_seconds` (default 5 minutes) for "has this learner
    been showing confusion/frustration lately", and the shorter
    `window_seconds` (the FusionWindow cadence, default 60s) for "did they
    already message the assistant in THIS decision window". A single
    shared window for both made the chat corroboration rule dead code -
    see FusionSignals' own field docstrings.

    Fails closed: a database problem returns empty chat signals (as if the
    learner had not chatted at all this window) rather than raising -
    matching this codebase's fail-silent convention for every other read
    on the live decision path. A missing chat signal degrades FusionPolicy
    to DefaultPolicy's own camera-only behavior, which is always safe.
    """
    resolved_now = now or datetime.now(timezone.utc)
    recent_emotion_signals: list[str] = []
    message_count = 0

    if engagement_signals.session_id is not None:
        if db is None:
            from app.core.db import db as _default_db
            db = _default_db
        try:
            from app.analytics.persistence.events import AssistantEventRepository
            from app.analytics.domain.metrics import _parse_datetime

            events = AssistantEventRepository(db).list_by_session(engagement_signals.session_id)
            learner_turns = [
                event for event in events
                if event.get("direction") == "learner"
            ]

            emotion_turns = [
                event for event in learner_turns
                if (resolved_now - _parse_datetime(event["timestamp"])).total_seconds() <= emotion_lookback_seconds
            ]
            emotion_turns.sort(key=lambda event: event["timestamp"])
            recent_emotion_signals = [event["learner_signal"] for event in emotion_turns]

            message_count = sum(
                1 for event in learner_turns
                if (resolved_now - _parse_datetime(event["timestamp"])).total_seconds() <= window_seconds
            )
        except Exception:
            log.warning(
                "fusion chat signals for session %s could not be read",
                engagement_signals.session_id, exc_info=True,
            )

    return FusionSignals(
        engagement=engagement_signals,
        recent_emotion_signals=recent_emotion_signals,
        assistant_message_count_last_60s=message_count,
        recovery_since_last_decision=recovery_since_last_decision,
    )

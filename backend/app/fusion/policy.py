"""
FusionPolicy - Module 6 (scope 6.6), the fusion-aware InterventionDecider.

Fusion rule (the one genuinely new judgement call this module makes, and
why it is conservative): Module 3's own tiers (policy.py's DefaultPolicy)
were empirically measured against labeled DAiSEE data. There is no
equivalent labeled data for "does chat confusion/frustration, combined
with camera state, actually predict genuine struggling" - no dataset
pairs real chat transcripts with real camera engagement labels for this
system. So the measured signal (camera, via DefaultPolicy) stays the
primary decision driver; chat only ever nudges within an already-camera-
silent decision, or participates in sequencing - it never invents a
simplify_content/bullet_summary decision on its own, because only the
camera signal has been measured at the tier level those interventions need.

See docs/superpowers/specs/2026-09-30-module-6-fusion-design.md section 5.
"""

from app.fusion.sequencing import next_sequence
from app.fusion.signals import build_fusion_signals
from app.fusion.window import FusionWindow
from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    REASON_OTHER,
    TIER_BROAD,
    Decision,
    Signals,
)
from app.intervention.policy import DefaultPolicy

POLICY_VERSION = "v1-fusion"

# >= this many of the recent chat turns must show confusion/frustration
# before chat is allowed to trigger anything on its own - one stray turn
# is not "sustained". An explicit, documented, NOT claimed as measured
# threshold - see the module docstring.
CHAT_CORROBORATION_COUNT = 2


class FusionPolicy:
    policy_version = POLICY_VERSION

    def __init__(self, base: "DefaultPolicy | None" = None):
        self._base = base or DefaultPolicy()
        self._window = FusionWindow()

    def decide(self, signals: Signals, *, history: list = None, recovery=None) -> Decision | None:
        history = history or []
        uid = signals.uid
        session_id = signals.session_id
        now = _now_seconds()

        bypasses_window = signals.state == "fatigued"
        if not bypasses_window and not self._window.ready(uid, session_id, now):
            return None

        fusion_signals = build_fusion_signals(
            signals, recovery_since_last_decision=recovery,
        )

        base_decision = self._base.decide(signals, history=history, recovery=recovery)

        if base_decision is None:
            base_decision = self._chat_only_decision(fusion_signals)
            if base_decision is None:
                # Deliberately does NOT mark the window here. Only a real
                # decision starts the 60s cadence - marking it on a quiet
                # outcome would silence reconsideration for the next ~59s
                # even while the learner starts struggling moments later.
                # "Don't re-fire too soon" after an actual intervention is
                # already cooldown's job (service.py), not this window's.
                return None

        decision = next_sequence(
            base_decision,
            history=history,
            recovery_since_last_decision=fusion_signals.recovery_since_last_decision,
            discouraged_types=signals.discouraged_types,
        )
        if not bypasses_window:
            self._window.mark_decided(uid, session_id, now)
        return decision

    @staticmethod
    def _chat_only_decision(fusion_signals) -> Decision | None:
        confused_or_frustrated = sum(
            1 for value in fusion_signals.recent_emotion_signals
            if value in ("confusion", "frustration")
        )
        already_asked = fusion_signals.assistant_message_count_last_60s > 0
        if confused_or_frustrated < CHAT_CORROBORATION_COUNT or already_asked:
            return None
        return Decision(
            intervention_type=ASSISTANT_HELP_PROMPT,
            reason_code=REASON_OTHER,
            reason="Recent messages showed sustained confusion or frustration - offered the assistant.",
            tier=TIER_BROAD,
            chunk_id=fusion_signals.engagement.chunk_id,
            content_id=fusion_signals.engagement.content_id,
            triggering_engagement_event_id=fusion_signals.engagement.engagement_event_id,
        )


def _now_seconds() -> float:
    import time

    return time.monotonic()

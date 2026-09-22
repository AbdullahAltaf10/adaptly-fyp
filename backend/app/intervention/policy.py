"""
The default intervention policy: tiered by how intrusive the response is.

Where the tiers come from
-------------------------
Measured, not argued. `ml/evaluation/trigger_fusion.py` scored every
combination of the two available signals on DAiSEE's held-out split, using the
per-subject-centred model:

    rule                   coverage    lift  flag rate
    LSTM argmax                9/19   1.83x      0.051
    LSTM tau=0.34             15/19   1.29x      0.214
    brow rule k=1.0           12/19   0.99x      0.105
    OR  argmax+brow           14/19   1.20x      0.140
    AND argmax+brow            4/19   1.82x      0.016

"lift" is Struggling precision divided by the class base rate. At or below 1.0
a trigger is no better than firing at random.

Two things fell out of that table:

  AND reaches only 4 of 19 learners, so it is useless as a trigger - but at
  1.82x it is the most reliable signal anywhere in this system.

  OR reaches 14 of 19 at a flag rate of 0.140, against 15 of 19 at 0.214 for
  the model alone. One fewer learner for 35% fewer interruptions, which
  matters because scope 6.4 asks for "infrequent targeted support".

So neither is "the trigger". STRONG gates the intrusive responses, BROAD gates
the gentle ones. This is the same cost-asymmetry argument that produced the
Struggling threshold, applied per intervention type instead of globally.

What this policy deliberately does not do
-----------------------------------------
It does not escalate. Scope 6.6 gives sequencing to Module 6, and doing it
honestly needs to know mid-session whether the last intervention helped, which
is not available yet (issue #45). A fake escalation that never checks whether
the previous step worked would be worse than none.
"""

import uuid

from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    BREAK_SUGGESTION,
    BULLET_SUMMARY,
    REASON_FATIGUE,
    REASON_STRUGGLING,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    TIER_RULE,
    TIER_STRONG,
    Decision,
    Signals,
)

POLICY_VERSION = "v1-tiered"

# Dwell thresholds, in seconds on the current chunk.
#
# Parameters rather than module constants on purpose: scope 6.9 requires the
# intervention engine to lower its threshold for HR-tagged critical
# paragraphs, so a constant here would force a signature change when Module 9
# lands.
#
# The values are starting points, NOT measured. DAiSEE has no dwell signal, so
# nothing in ml/evaluation/ can justify a number here. They need tuning against
# real sessions once a content viewer exists, and should be treated as
# provisional until then.
DEFAULT_DWELL_LONG = 45.0
DEFAULT_DWELL_SHORT = 15.0

# How much a critical section lowers both gates (scope 6.9, "respond earlier
# where comprehension matters most"). Also provisional.
CRITICAL_DWELL_FACTOR = 0.5


class DefaultPolicy:
    """
    The tiered policy. Pure: same inputs, same output, no I/O, no clock.

    Cooldown is deliberately NOT handled here. A policy that also owned timing
    would be untestable without freezing time, and the caller has to consult
    cooldown before asking anyway.
    """

    policy_version = POLICY_VERSION

    def __init__(
        self,
        dwell_long: float = DEFAULT_DWELL_LONG,
        dwell_short: float = DEFAULT_DWELL_SHORT,
        critical_factor: float = CRITICAL_DWELL_FACTOR,
    ):
        if not 0 < critical_factor <= 1:
            raise ValueError("critical_factor must be in (0, 1]")
        if dwell_short > dwell_long:
            raise ValueError("dwell_short must not exceed dwell_long")
        self.dwell_long = dwell_long
        self.dwell_short = dwell_short
        self.critical_factor = critical_factor

    def gates_for(self, signals: Signals) -> tuple[float, float]:
        """Dwell gates for this chunk, lowered when HR has marked it critical."""
        factor = self.critical_factor if signals.is_critical else 1.0
        return self.dwell_long * factor, self.dwell_short * factor

    def decide(self, signals: Signals, *, history=None, recovery=None) -> Decision | None:
        history = history or []

        # Fatigue sits outside the tiers. It is a rule state with its own
        # evidence - fatigue_ratio, which since the confidence fix is what the
        # engagement event's `confidence` actually carries - so it does not
        # need the model's agreement to be trusted.
        if signals.state == "fatigued":
            return Decision(
                intervention_type=BREAK_SUGGESTION,
                reason_code=REASON_FATIGUE,
                reason="Sustained low eye openness suggested tiredness.",
                tier=TIER_RULE,
                chunk_id=signals.chunk_id,
                content_id=signals.content_id,
                triggering_engagement_event_id=signals.engagement_event_id,
            )

        strong = signals.raw_struggling and signals.brow_struggling
        broad = signals.raw_struggling or signals.brow_struggling
        if not broad:
            return None

        long_gate, short_gate = self.gates_for(signals)

        # Rewriting what somebody is reading is the most intrusive thing this
        # system does, so it needs the strongest evidence AND sustained dwell.
        if strong and signals.dwell_seconds >= long_gate:
            return Decision(
                intervention_type=SIMPLIFY_CONTENT,
                reason_code=REASON_STRUGGLING,
                reason=(
                    f"Both the engagement model and the brow signal indicated "
                    f"difficulty while you stayed on this section for "
                    f"{int(signals.dwell_seconds)}s."
                ),
                tier=TIER_STRONG,
                chunk_id=signals.chunk_id,
                content_id=signals.content_id,
                triggering_engagement_event_id=signals.engagement_event_id,
            )

        # A summary changes nothing the learner is reading, so weaker evidence
        # is acceptable - but it still only makes sense once they have been on
        # the section long enough for there to be something to summarise.
        if signals.dwell_seconds >= short_gate:
            return Decision(
                intervention_type=BULLET_SUMMARY,
                reason_code=REASON_STRUGGLING,
                reason=(
                    f"Signs of difficulty on this section after "
                    f"{int(signals.dwell_seconds)}s."
                ),
                tier=TIER_BROAD,
                chunk_id=signals.chunk_id,
                content_id=signals.content_id,
                triggering_engagement_event_id=signals.engagement_event_id,
            )

        # Cheapest response, so it takes the weakest evidence and no dwell gate.
        return Decision(
            intervention_type=ASSISTANT_HELP_PROMPT,
            reason_code=REASON_STRUGGLING,
            reason="Signs of difficulty; offered the assistant.",
            tier=TIER_BROAD,
            chunk_id=signals.chunk_id,
            content_id=signals.content_id,
            triggering_engagement_event_id=signals.engagement_event_id,
        )


def new_intervention_id() -> str:
    return str(uuid.uuid4())

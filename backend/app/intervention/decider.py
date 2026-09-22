"""
The interface between deciding to intervene and actually intervening.

Why this is a separate file
---------------------------
Scope 6.4 gives Module 4 the job of deciding what response to give. Scope 6.6
then gives Module 6 the job of deciding "what type of support is most likely to
help", and of planning responses "in sequences rather than single isolated
actions".

Those overlap. If Module 4 hard-codes its decision, Module 6 arrives and either
duplicates it or replaces it, and one of them gets thrown away.

So the decision is a strategy, not a function:

    InterventionDecider   the interface
      DefaultPolicy       the tiered rules in policy.py - this module, now
      FusionPolicy        camera + chat + content, sequences - Module 6, later

The executor takes a Decision and delivers it. It never asks why. Module 6 then
lands as a second implementation of an interface that already exists rather
than as a rewrite.

A sequence needs no new machinery either: a decider that plans sequences is
just one that remembers what it already tried, which is what `history` and
`recovery` carry.
"""

from dataclasses import dataclass
from typing import Protocol

# Mirrors intervention-event.schema.json. Named here so a typo becomes an
# import error rather than an event the contract rejects at the boundary.
SIMPLIFY_CONTENT = "simplify_content"
BULLET_SUMMARY = "bullet_summary"
BREAK_SUGGESTION = "break_suggestion"
ASSISTANT_HELP_PROMPT = "assistant_help_prompt"
OTHER = "other"

INTERVENTION_TYPES = (
    SIMPLIFY_CONTENT,
    BULLET_SUMMARY,
    BREAK_SUGGESTION,
    ASSISTANT_HELP_PROMPT,
    OTHER,
)

REASON_DRIFTING = "drifting"
REASON_STRUGGLING = "struggling"
REASON_FATIGUE = "fatigue"
REASON_READING_DIFFICULTY = "reading_difficulty"
REASON_REPEATED_DIFFICULTY = "repeated_difficulty"
REASON_OTHER = "other"

REASON_CODES = (
    REASON_DRIFTING,
    REASON_STRUGGLING,
    REASON_FATIGUE,
    REASON_READING_DIFFICULTY,
    REASON_REPEATED_DIFFICULTY,
    REASON_OTHER,
)

# Which evidence tier fired. Not part of the contract - it is an internal
# record of how much the decider trusted itself, kept because
# ml/evaluation/trigger_fusion.py measured the two tiers as very different
# things and a later reader will want to know which one produced an event.
TIER_STRONG = "strong"
TIER_BROAD = "broad"
TIER_RULE = "rule"


@dataclass(frozen=True)
class Signals:
    """
    Everything a decider is allowed to see.

    Deliberately not the raw engagement event. A decider that reads the event
    dict directly ends up coupled to Module 3's internals, and every change
    there becomes a change here. This is the agreed surface instead.

    `raw_struggling` and `brow_struggling` are kept separate rather than
    pre-combined because the two tiers in policy.py need them separately, and
    because they were measured separately - see ml/evaluation/trigger_fusion.py.
    """

    state: str                      # the reported state, post-smoothing
    source: str                     # lstm | rule | hybrid
    confidence: float               # confidence in `state`, not in some other class
    raw_struggling: bool            # the model's own class was struggling
    brow_struggling: bool           # the per-user brow rule fired
    chunk_id: str | None = None
    content_id: str | None = None
    is_critical: bool = False       # set by Module 9; always False until then
    dwell_seconds: float = 0.0      # time on this chunk; 0 until a viewer exists
    engagement_event_id: str | None = None


@dataclass(frozen=True)
class Decision:
    """
    What to do. Carries its own justification so the event can be built
    without the executor having to reconstruct why.

    `sequence_id` and `step_index` are here but not yet in the contract - see
    issue #45. Keeping them on the Decision now means a sequencing decider can
    be written before the schema catches up, and the executor drops them until
    the contract accepts them.
    """

    intervention_type: str
    reason_code: str
    reason: str                     # one plain sentence, shown in Module 8's log
    tier: str
    chunk_id: str | None = None
    content_id: str | None = None
    triggering_engagement_event_id: str | None = None
    sequence_id: str | None = None
    step_index: int | None = None

    def __post_init__(self):
        if self.intervention_type not in INTERVENTION_TYPES:
            raise ValueError(f"unknown intervention_type: {self.intervention_type}")
        if self.reason_code not in REASON_CODES:
            raise ValueError(f"unknown reason_code: {self.reason_code}")


class InterventionDecider(Protocol):
    """
    Implemented by DefaultPolicy now, and by Module 6's fusion policy later.

    `history` is this session's interventions, most recent last. `recovery` is
    an optional view of whether earlier interventions helped - it stays None
    until issue #45 makes recovery evaluation available mid-session, and a
    decider that needs it should say so rather than guessing.
    """

    policy_version: str

    def decide(
        self,
        signals: Signals,
        *,
        history: list,
        recovery=None,
    ) -> Decision | None:
        """Return what to deliver, or None to stay silent."""
        ...

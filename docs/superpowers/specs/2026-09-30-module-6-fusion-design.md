# Module 6 — CV+AI Integration Layer (Fusion): Design

**Status:** approved for implementation (user: "check the scope and compare and now dont ask me any questions start coding" — spec/plan review gates skipped on explicit instruction; this document still exists as the record of what was decided and why).

## 1. Scope

Scope document section 6.6 (verbatim): "Every 60 seconds it receives three inputs at the same time: the camera-based engagement data, the agent conversation history, and the current content being studied. It combines all three to produce a unified understanding of what the user is struggling with, how long it has been happening, and what type of support is most likely to help... It plans responses in sequences rather than single isolated actions. If one approach does not help, it moves to the next planned step."

The 91% fusion-accuracy figure scope cites (Gong 2025) is a voice+video study; this project does no voice analysis (scope explicitly excludes it: "does not support... voice emotion analysis"). That number is not a target here and is not claimed anywhere in this implementation.

## 2. What already exists (nothing built from zero)

| Need | Already here |
|---|---|
| A seam Module 6 can plug into without touching delivery | `app/intervention/decider.py`'s `InterventionDecider` Protocol + `service.set_decider()` |
| Camera-side signals | Module 3's full output: `state`, `raw_struggling`, `brow_struggling`, `paragraph_revisit_detected`, `is_critical`, `dwell_seconds` (all already on `Signals`) |
| Chat-side signals | Module 5's `emotion_signal` (confusion/frustration/neutral) per exchange, and `input_mode`, persisted via `record_assistant_exchange` |
| Sequencing fields | `Decision.sequence_id` / `step_index` already exist (not yet in the JSON contract — see §6) |
| History | `store.list_for_session(session_id)` |
| Escalation ladder (implicit) | `DefaultPolicy`'s own tier order: `simplify_content` (strong+long dwell) → `bullet_summary` (broad+short dwell) → `assistant_help_prompt` (broad, no dwell gate) — cheapest-first, already measured against DAiSEE (`policy.py`'s own docstring table) |
| "Did the last intervention help?" | **Not available live** — `_observed_recovery` (`app/analytics/domain/metrics.py`) exists and is correct, but only ever called post-session, in batch, by `calculate_recoveries`. This is issue #45, the blocker for honest sequencing, and is Phase 0 below. |

**Net:** Module 6 is a second implementation of `InterventionDecider`, not a new subsystem grafted on top of one.

## 3. Phase 0 — live-callable recovery (issue #45)

**New function**, `app/analytics/domain/metrics.py`:

```python
def observed_recovery_since(
    uid: str,
    session_id: str,
    since: datetime,
    *,
    now: datetime | None = None,
    config: MetricConfig = DEFAULT_CONFIG,
) -> bool:
    """Has this learner shown 2 consecutive focused/recovered confirmations
    (within gap_tolerance_seconds) since `since`? Mid-session, no waiting for
    session end. Reuses _observed_recovery's own confirmation-counting logic
    unchanged - this is a new caller, not a new algorithm."""
```

Implementation: fetch this session's engagement events since `since` via `EngagementEventRepository(db).list_by_session(session_id)` (already exists, used today by post-session finalization — filter the returned list to `timestamp >= since` here rather than adding a new repository method), then run the same confirmation-counting loop `_observed_recovery` already has (extracted as a small shared helper if that keeps both callers honest, or called through a thin wrapper — decided during implementation, not a design commitment either way). `calculate_recoveries` and `_observed_recovery` itself are not modified.

**Wiring into the live path** (`app/intervention/service.py`, `evaluate()`): today `_decider.decide(signals, history=history, recovery=None)` hardcodes `None` — no decider has ever been able to see live recovery, even though the `Signals`/`Decision`/Protocol surface has always accepted it. After Phase 0:

```python
last_decision_at = _last_decision_timestamp(history)  # None if no prior decision this session
recovery = (
    observed_recovery_since(uid, session_id, last_decision_at)
    if last_decision_at is not None
    else None
)
decision = _decider.decide(signals, history=history, recovery=recovery)
```

`DefaultPolicy.decide()` already accepts `recovery=None` as a keyword and ignores it — passing a real value now costs it nothing; it simply continues to ignore what it does not use. Only `FusionPolicy` (Phase 2) reads it.

## 4. Phase 1 — `app/fusion/signals.py` + `app/fusion/window.py`

New package, nothing in `app/intervention/` touched (this is the whole point of the interface boundary).

```python
# app/fusion/signals.py
@dataclass(frozen=True)
class FusionSignals:
    engagement: Signals                        # Module 3/4's existing Signals, reused as-is
    recent_emotion_signals: list[str]           # M5 exchanges in the trailing window, most recent last
    assistant_message_count_last_60s: int       # "did the learner ask for help?" - scope's own framing:
                                                 # a struggling learner is the LEAST likely to ask
    recovery_since_last_decision: bool | None   # from Phase 0; None only if there was no prior decision
```

`window.py`: "every 60 seconds" (scope's own wording) is implemented as an accumulator inside `FusionPolicy.decide()` itself, not a new polling loop — Module 3 already calls in every second via `/engagement/analyze`, Module 5 calls in whenever the learner asks a question. Introducing a second scheduled loop would add latency and complexity scope never asked for. Instead: `decide()` is called every time `evaluate()` already runs (every ~1s), and internally tracks whether 60 real seconds have passed since its last actual decision for this session; if not, it defers to the same behavior `DefaultPolicy` already has for "nothing to say" (return `None`) **except** for `fatigued`, which is allowed to react immediately regardless of the 60s gate — a rule-based, already-certain signal, and scope 6.4's "timely support" argument applies here exactly as it does in `DefaultPolicy` today.

```python
# app/fusion/window.py
class FusionWindow:
    """Per-(uid, session_id) 60-second gate. Pure bookkeeping, no I/O."""
    def ready(self, uid: str, session_id: str, now: float) -> bool: ...
    def mark_decided(self, uid: str, session_id: str, now: float) -> None: ...
```

In-memory, keyed by `(uid, session_id)`, same lifecycle pattern as `engagement/smoothing.py` and `intervention/cooldown.py` (dies on restart, single-worker limitation — an already-accepted, documented limitation elsewhere in this codebase, not a new one).

## 5. Phase 2 — `app/fusion/policy.py` (`FusionPolicy`)

Implements `InterventionDecider`. Fusion rule, per the approved design decision: **chat is a tie-breaker/booster, never an independent trigger.**

Why (this is the one genuinely new judgment call in this module, and it is deliberately conservative): Module 3's own tiers were empirically measured against labeled DAiSEE data (`policy.py`'s own docstring table). There is no equivalent labeled data for "does chat confusion/frustration, combined with camera state, actually predict genuine struggling" — no dataset exists that pairs real chat transcripts with real camera engagement labels for this system. Claiming a *measured* combination rule here would be dishonest in exactly the way the project's own model card goes out of its way never to be (FINDINGS.md's whole discipline: never claim more certainty than the data supports). So: the one signal that has been measured (camera, via `DefaultPolicy`'s own tiers) stays the primary decision driver, and chat can only nudge within that already-earned decision — never manufacture one on its own.

Concretely:

```python
class FusionPolicy:
    policy_version = "v1-fusion"

    def __init__(self, base: InterventionDecider = None):
        self._base = base or DefaultPolicy()   # reuse the measured tiers, do not re-derive them
        self._window = FusionWindow()

    def decide(self, signals: Signals, *, history: list, recovery=None) -> Decision | None:
        # signals here is actually FusionSignals - see §7 for the adapter that
        # builds it; base decider calls still take plain Signals.
        ...
```

Behavior:
1. `fatigued` bypasses the 60s window entirely (same reasoning as `DefaultPolicy`).
2. Otherwise, gated on `FusionWindow.ready(...)`. Not ready → `None` (same as "nothing to say" today).
3. When ready: ask `self._base.decide(signals.engagement, history=history, recovery=recovery)` for the camera-only decision first.
4. If the base decision is `None` **and** `recent_emotion_signals` shows sustained confusion/frustration (≥2 of the last 3 chat turns, a small, explicit, documented threshold — not claimed as measured) **and** `assistant_message_count_last_60s == 0` (the learner hasn't already asked for help through the normal panel route — scope's own "struggling learners ask least" framing, so silence plus chat-signalled confusion is the one case worth a gentle nudge): offer `ASSISTANT_HELP_PROMPT` at `TIER_BROAD`, reason code `REASON_OTHER`, with an honest reason string naming this as a chat-signal-only trigger (so Module 8's log and any future audit can tell it apart from a camera-measured one).
5. If the base decision is **not** `None`: chat can only affect *tier*, never *type* — if `recent_emotion_signals` corroborates (recent confusion/frustration present) the base decision's tier is left as-is; chat never downgrades or upgrades intervention *type* selection, only ever participates in the already-existing sequencing/escalation decision in step 6.
6. Sequencing (Phase 4's `sequence_id`/`step_index`): if `recovery_since_last_decision is False` and the base decider's own natural next-tier choice would repeat the same `intervention_type` as the immediately preceding one in `history`, escalate one step up `DefaultPolicy`'s own ladder (`assistant_help_prompt` → `bullet_summary` → `simplify_content`) instead, carrying the previous `sequence_id` forward and incrementing `step_index`. If `recovery_since_last_decision is True`, or there is no prior decision this session, start a new `sequence_id` at `step_index=0`. If `recovery_since_last_decision is None` (Phase 0 had nothing to report - e.g. no prior decision yet), behave exactly as `DefaultPolicy` does today: no escalation, matching `policy.py`'s own documented "no escalation without a real recovery signal" stance until this point.

**What this deliberately does not do:** it does not invent a new struggling-detection path from chat alone strong enough to fire `simplify_content` or `bullet_summary` — those stay camera-gated, because only the camera signal has ever been measured at the tier level those interventions need.

## 6. Phase 3 — wiring

One line, feature-flagged:

```python
# app/main.py startup, or a dedicated settings read - decided at implementation time
if os.getenv("ADAPTLY_FUSION_POLICY") == "1":
    from app.fusion.policy import FusionPolicy
    intervention_service.set_decider(FusionPolicy())
```

Default is **off** (`DefaultPolicy` stays the shipped behavior) — this mirrors how the calibrated model pair only activates for a learner who has actually calibrated (`ml/inference/model.py`'s own "two artifact pairs" design): a policy that has never been measured against a live session should not become everyone's default the moment it merges. Flipping it on is a one-line env var change whenever there's confidence to do so.

**Contract note:** `contracts.py` (`build_intervention_event`) already writes `sequence_id`/`step_index` onto the event when the `Decision` carries them (lines 172-175, confirmed in code) — no schema change needed, matching `decider.py`'s own docstring claim.

Test that pins the whole promise (already written, per the research doc): `test_module_6_can_replace_the_policy_without_touching_delivery` (`test_intervention_lifecycle.py:536`) — confirmed to exist; re-run as part of Phase 3 to prove `FusionPolicy` satisfies it without modification to any Module 4 delivery file.

## 7. Phase 4 — `app/fusion/sequencing.py`

Small, focused module: given `history` (this session's prior `Decision`-derived events) and the current base decision, decides whether to carry forward a `sequence_id`/bump `step_index` or start fresh, per §5 step 6's rule. Separated from `policy.py` itself so the escalation-ladder bookkeeping is independently testable without re-exercising the whole fusion decision each time.

Also needed here: an adapter that builds `FusionSignals` from what `service.evaluate()` currently has in scope (camera `Signals`, already built) plus what it does not yet have — recent `emotion_signal` history and assistant-message counts for this session in the last 60s. This requires a small new read path: `app/fusion/signals.py` gains a `build_fusion_signals(uid, session_id, engagement_signals, ...)` that queries the assistant-exchange analytics store (`record_assistant_exchange`'s own collection, already written on every `/assistant/messages` call per Module 5) for the trailing window. Read-only, no new writes.

## 8. Frontend impact

**Unchanged:** `useIntervention.js`, `InterventionHost.jsx`, `ParagraphPopup.jsx`, `useDwell.js`, `/intervention/{id}/status`, `/intervention/{id}/content` — all consume whatever `Decision` the active decider produced; none of them know or care which decider ran. This is the architecture's entire payoff.

**Small, optional:** `StudySession.jsx`'s dev-only `Diagnostics` panel gains `sequence_id`/`step_index` display when present (never shown to the learner outside that collapsed disclosure — scope 6.8).

## 9. Testing

Same discipline as every other task this session: TDD (failing test first, confirmed failing for the right reason), mutation-checked, ledgered. Specifically:

- Phase 0: `observed_recovery_since` tested against the same confirmation-counting scenarios `_observed_recovery` already has coverage for (2 consecutive within gap tolerance = True, interrupted sequence = False, nothing since `since` = False), plus the `service.py` wiring test (recovery passed through only when a prior decision exists this session).
- Phase 1: `FusionSignals` construction and `FusionWindow`'s 60s gate (ready/not-ready, fatigue bypass) - pure logic, no I/O, no mocking needed beyond a fake clock.
- Phase 2: `FusionPolicy.decide()` - camera-decision-preserved-when-present, chat-only-trigger-when-camera-silent-and-corroborated, chat-never-changes-type-when-camera-already-decided, escalation-on-non-recovery, fresh-sequence-on-recovery, no-escalation-when-recovery-is-None (matches `DefaultPolicy`'s current behavior exactly in that case - a non-regression requirement).
- Phase 3: the pinned integration test, re-run; a new test that the feature flag actually switches deciders.
- Phase 4: sequencing in isolation (given a history + a same-type repeat + recovery=False → escalates; given recovery=True → fresh sequence).

## 10. Explicitly out of scope for this spec

- Module 3's gaze-regression classifier (OneStop dataset, 1D-CNN/SVM) — independent of Module 6 per the research doc's own §10.3 ("Module 6 Module 3 ke gaze-regression pe depend NAHI karta"), a separate multi-week ML sub-project, not started here.
- Retraining or re-measuring Module 3's own tiers - untouched.
- Any new frontend surface for sequences beyond the existing dev-only Diagnostics panel.

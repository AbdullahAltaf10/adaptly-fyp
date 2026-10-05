# Module 6 — CV+AI Integration Layer (Fusion) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Module 6 (scope 6.6) as a second implementation of the existing `InterventionDecider` interface — `FusionPolicy` — that combines camera signals (Module 3), chat signals (Module 5), content, and live mid-session recovery evidence (issue #45, the prerequisite this plan builds first) into sequenced intervention decisions, without touching any delivery code.

**Architecture:** Phase 0 makes recovery checkable mid-session (a new function in `app/analytics/domain/metrics.py`, reusing `_observed_recovery`'s existing logic) and wires it into `service.evaluate()`. Phases 1-4 build a new `app/fusion/` package (`signals.py`, `window.py`, `sequencing.py`, `policy.py`) that is wired in behind an environment-variable feature flag, defaulting off. Module 3/4's own delivery files (`useIntervention.js`, `InterventionHost.jsx`, the `/intervention/*` routes) are untouched — they already only know how to render whatever `Decision` the active decider produced.

**Tech Stack:** Python/FastAPI backend, MongoDB (pymongo via `app.core.db.db`), pytest, existing `app.analytics.persistence.events` repositories.

**Spec:** `docs/superpowers/specs/2026-09-30-module-6-fusion-design.md`

## Global Constraints

- Never run `git commit` — only `git add` to stage (standing project rule; commits happen later, separately).
- Never touch `backend/.venv`, `frontend/node_modules`, `sibtain-workspace/.venv-ml`.
- The real repo is `D:\fypproject\adaptly-fyp`.
- `Signals` (`app/intervention/decider.py`) gains two new optional fields (`uid`, `session_id`, both `str | None = None`) in Task 2 — additive, backward-compatible, needed because `FusionPolicy.decide()` must conform to the exact `InterventionDecider.decide(signals, *, history, recovery=None)` signature (it cannot take extra positional/keyword arguments `service.evaluate()` doesn't already pass) but still needs to look up this learner's own recent chat history. This is the one, minimal, justified touch to `app/intervention/decider.py` in this whole plan — `DefaultPolicy` ignores both new fields, so nothing about its behavior changes.
- TDD throughout: write the failing test, confirm it fails for the stated reason, implement, confirm it passes, mutation-check the core logic change, then stage.
- Ledger progress in `.superpowers/sdd/2026-09-30-module-6-fusion-plan/progress.md` (created fresh, matching this session's established pattern in the two prior plans' ledgers).

## Review Focus

- **`observed_recovery_since` called with `since` in the future or equal to `now`** — must return `False` cleanly (no negative-duration windows, no crash), not raise. Pinned in Task 1.
- **`FusionWindow.ready()` called for a `(uid, session_id)` pair that has never been seen before** — must return `True` (a session's first-ever fusion decision should not be blocked by a 60-second wait that never had a "previous decision" to measure from). Pinned in Task 5.
- **`build_fusion_signals` when there are zero assistant exchanges this session** — must return `recent_emotion_signals=[]` and `assistant_message_count_last_60s=0`, never raise on an empty history. Pinned in Task 4.
- **`FusionPolicy.decide()` when the base `DefaultPolicy` already returned a non-`None` decision and chat signals are also present** — chat must never change `intervention_type`, only ever participate in the separate sequencing decision. Pinned in Task 7 (this is the spec's most safety-critical rule: the whole reason chat is a tie-breaker and not an independent trigger).
- **`sequencing.next_sequence(...)` when `history` contains interventions from a *different* session or a stale/malformed entry missing `intervention_type`** — must not crash; the spec's escalation rule only looks at the immediately-preceding entry, so a defensively-written `.get(...)` read (not a bare `[...]` index) is the right shape here. Pinned in Task 6.

---

### Task 1: `observed_recovery_since` — live-callable recovery (issue #45, part 1)

**Files:**
- Modify: `backend/app/analytics/domain/metrics.py`
- Test: `backend/tests/analytics/test_metrics.py` (existing file — extend)

**Interfaces:**
- Consumes: `_observed_recovery` (existing, same file), `_parse_datetime` (existing, same file), `EngagementEventRepository` (`app/analytics/persistence/events.py`, existing).
- Produces: `observed_recovery_since(uid: str, session_id: str, since: datetime, *, now: datetime | None = None, config: MetricConfig = DEFAULT_CONFIG, db=None) -> bool`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/analytics/test_metrics.py`, near the other recovery tests (after `test_explicit_recovery_duration_is_derived_from_timestamps`, following the existing file's style):

```python
    def test_observed_recovery_since_is_false_with_no_events(self) -> None:
        from app.analytics.domain.metrics import observed_recovery_since

        class EmptyRepo:
            def list_by_session(self, session_id: str) -> list[dict]:
                return []

        result = observed_recovery_since(
            "user-1", "session-1", _parse(timestamp(0)),
            now=_parse(timestamp(60)), db=FakeDatabase(EmptyRepo()),
        )
        self.assertFalse(result)

    def test_observed_recovery_since_is_true_after_two_consecutive_focused_confirmations(self) -> None:
        from app.analytics.domain.metrics import observed_recovery_since

        events = [
            engagement(10, "focused", event_number=1),
            engagement(15, "focused", event_number=2),
        ]

        class FixedRepo:
            def list_by_session(self, session_id: str) -> list[dict]:
                return events

        result = observed_recovery_since(
            "user-1", "session-1", _parse(timestamp(0)),
            now=_parse(timestamp(60)), db=FakeDatabase(FixedRepo()),
        )
        self.assertTrue(result)

    def test_observed_recovery_since_ignores_events_before_since(self) -> None:
        """Two focused confirmations exist, but both are BEFORE `since` - they
        must not count as recovery from a decision made after them."""
        from app.analytics.domain.metrics import observed_recovery_since

        events = [
            engagement(0, "focused", event_number=1),
            engagement(5, "focused", event_number=2),
            engagement(10, "struggling", event_number=3),
        ]

        class FixedRepo:
            def list_by_session(self, session_id: str) -> list[dict]:
                return events

        result = observed_recovery_since(
            "user-1", "session-1", _parse(timestamp(8)),
            now=_parse(timestamp(60)), db=FakeDatabase(FixedRepo()),
        )
        self.assertFalse(result)

    def test_observed_recovery_since_handles_since_in_the_future_without_raising(self) -> None:
        """`since` at or after `now` is a degenerate but real caller mistake
        (e.g. clock skew) - must return False, never raise."""
        from app.analytics.domain.metrics import observed_recovery_since

        class EmptyRepo:
            def list_by_session(self, session_id: str) -> list[dict]:
                return []

        result = observed_recovery_since(
            "user-1", "session-1", _parse(timestamp(120)),
            now=_parse(timestamp(60)), db=FakeDatabase(EmptyRepo()),
        )
        self.assertFalse(result)

    def test_observed_recovery_since_never_raises_when_the_repository_fails(self) -> None:
        """Matches this codebase's fail-silent convention for every other
        engagement-adjacent read (engagement/analytics_sink.py, intervention/
        store.py): a database problem must return a safe default, not crash
        a live decision path."""
        from app.analytics.domain.metrics import observed_recovery_since

        class BrokenRepo:
            def list_by_session(self, session_id: str) -> list[dict]:
                raise RuntimeError("db down")

        result = observed_recovery_since(
            "user-1", "session-1", _parse(timestamp(0)),
            now=_parse(timestamp(60)), db=FakeDatabase(BrokenRepo()),
        )
        self.assertFalse(result)
```

Add these two small helpers near the top of the same test class (or as module-level functions right above the class, matching the file's existing `_schema_type_matches`-style module-level helper placement):

```python
def _parse(value: str) -> datetime:
    from app.analytics.domain.metrics import _parse_datetime
    return _parse_datetime(value)


class FakeDatabase:
    """Stands in for the pymongo database `EngagementEventRepository(db)`
    expects - only `__getitem__` is ever called on it, and only to hand back
    a fake collection whose `.find(...)` behavior this test controls via the
    injected repo's `list_by_session`."""

    def __init__(self, repo):
        self._repo = repo

    def __getitem__(self, _name):
        return self._repo
```

Note: `observed_recovery_since` takes `db` as an injectable parameter specifically so these tests can substitute a fake `EngagementEventRepository`-shaped object without needing a real MongoDB connection — this mirrors how `engagement/analytics_sink.py`'s tests stub `db` rather than connecting to a real database.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/analytics/test_metrics.py -v -k observed_recovery_since`
Expected: FAIL — `ImportError: cannot import name 'observed_recovery_since'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/analytics/domain/metrics.py`, add near `calculate_recoveries` (after it, so it reads as "the batch version, then the live version"):

```python
def observed_recovery_since(
    uid: str,
    session_id: str,
    since: datetime,
    *,
    now: datetime | None = None,
    config: MetricConfig = DEFAULT_CONFIG,
    db=None,
) -> bool:
    """Has this learner shown recovery (config.recovery_confirmation_samples
    consecutive focused/recovered confirmations within
    config.gap_tolerance_seconds) since `since`? Mid-session, no waiting for
    session end - issue #45. Reuses _observed_recovery's own
    confirmation-counting logic unchanged; this is a new caller; the
    post-session calculate_recoveries path is not modified.

    `db` defaults to the app's lazy singleton connection - a parameter
    rather than a hardcoded import so tests can substitute a fake
    repository without a real MongoDB connection.

    Fails closed: a database problem, or `since >= now`, returns False
    rather than raising - matching this codebase's fail-silent convention
    for every other read on the live prediction path.
    """
    if db is None:
        from app.core.db import db as _default_db
        db = _default_db

    resolved_now = now or datetime.now(timezone.utc)
    if since >= resolved_now:
        return False

    try:
        from app.analytics.persistence.events import EngagementEventRepository

        events = EngagementEventRepository(db).list_by_session(session_id)
    except Exception:
        log.warning(
            "live recovery check for %s/%s could not read engagement events",
            uid, session_id, exc_info=True,
        )
        return False

    recovered_at, _duration = _observed_recovery(
        intervention={},  # no explicit recovery_timestamp path for a live check
        engagement_events=events,
        start=since,
        limit=resolved_now,
        competing_start=None,
        config=config,
    )
    return recovered_at is not None
```

Add the two missing imports at the top of the file if not already present (check the existing import block first — `datetime` and `timezone` are almost certainly already imported given `_parse_datetime` uses them; add a module-level `log = logging.getLogger(__name__)` and `import logging` only if genuinely absent):

```python
import logging
```
```python
log = logging.getLogger(__name__)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/analytics/test_metrics.py -v -k observed_recovery_since`
Expected: PASS, all 5 new tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS — purely additive function, no existing code path calls it yet.

- [ ] **Step 6: Mutation check**

Temporarily change `if since >= resolved_now: return False` to `if False: return False` (never short-circuits) and confirm `test_observed_recovery_since_handles_since_in_the_future_without_raising` fails (it would instead try to compute a negative-duration window through `_observed_recovery`, which returns `(None, None)` for an empty candidate list regardless — if the test still passes under this mutation, broaden it to assert the computed `limit` truly nets out non-negative by checking behavior with a real future-dated engagement event too; record in the ledger whichever outcome actually occurs). Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/analytics/domain/metrics.py backend/tests/analytics/test_metrics.py
```

---

### Task 2: Wire live recovery into `service.evaluate()`, and add `uid`/`session_id` to `Signals` (issue #45, part 2)

**Files:**
- Modify: `backend/app/intervention/decider.py`
- Modify: `backend/app/intervention/service.py`
- Test: `backend/tests/test_intervention_lifecycle.py` (existing file — extend)

**Interfaces:**
- Consumes: `observed_recovery_since` (Task 1).
- Produces: `Signals.uid: str | None = None`, `Signals.session_id: str | None = None` (additive fields); `service.evaluate()` now passes a real `recovery` value to `_decider.decide(...)` when a prior decision exists this session.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_intervention_lifecycle.py`, near `test_module_6_can_replace_the_policy_without_touching_delivery` (reuse that test's `AlwaysBreak`-style stub pattern):

```python
def test_recovery_is_passed_to_the_decider_when_a_prior_decision_exists_this_session(fake_store, monkeypatch):
    """Before issue #45's wiring, recovery was hardcoded to None regardless
    of what a decider could compute from it. This proves a decider now
    actually receives a real value once there is something to measure
    recovery from."""
    seen = []

    class RecordingDecider:
        policy_version = "test-recording"

        def decide(self, signals, *, history=None, recovery=None):
            seen.append(recovery)
            return None

    service.set_decider(RecordingDecider())
    monkeypatch.setattr(
        "app.intervention.service.observed_recovery_since",
        lambda uid, session_id, since, **kwargs: True,
    )

    # First decision this session: no prior decision to measure recovery
    # from, so recovery must stay None - there is nothing to have recovered
    # FROM yet.
    service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    assert seen[-1] is None

    # Second call: a prior decision now exists in history, so recovery must
    # be computed (and here, per the monkeypatched function, is True).
    service.evaluate(
        "u1", "s1", state="struggling", source="lstm", confidence=0.7,
        raw_struggling=True, brow_struggling=False,
    )
    assert seen[-1] is True


def test_signals_carries_uid_and_session_id_through_to_the_decider(fake_store):
    """FusionPolicy (Module 6) needs to look up this learner's own recent
    chat history, and the InterventionDecider Protocol's decide(signals, *,
    history, recovery=None) signature has no other place to carry identity -
    see decider.py's Signals dataclass."""
    seen = []

    class RecordingDecider:
        policy_version = "test-recording"

        def decide(self, signals, *, history=None, recovery=None):
            seen.append((signals.uid, signals.session_id))
            return None

    service.set_decider(RecordingDecider())
    service.evaluate(
        "u1", "s1", state="focused", source="lstm", confidence=0.9,
        raw_struggling=False, brow_struggling=False,
    )
    assert seen[-1] == ("u1", "s1")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_intervention_lifecycle.py -v -k "recovery_is_passed_to_the_decider or signals_carries_uid"`
Expected: FAIL — `test_signals_carries_uid_and_session_id_through_to_the_decider` fails with `AttributeError: 'Signals' object has no attribute 'uid'`; `test_recovery_is_passed_to_the_decider_when_a_prior_decision_exists_this_session` fails because `monkeypatch.setattr("app.intervention.service.observed_recovery_since", ...)` raises `AttributeError` (the name does not exist in that module yet).

- [ ] **Step 3: Add the fields and the wiring**

In `backend/app/intervention/decider.py`, add two fields to `Signals` (after `paragraph_revisit_detected`, the dataclass's last existing field):

```python
    # Needed only by a decider that looks up its own additional context
    # (Module 6's FusionPolicy reads a learner's recent chat history) - the
    # InterventionDecider Protocol's decide() signature has no other place
    # to carry identity. DefaultPolicy ignores both; purely additive.
    uid: str | None = None
    session_id: str | None = None
```

In `backend/app/intervention/service.py`, add the import:

```python
from app.analytics.domain.metrics import observed_recovery_since
```

Add `uid=uid, session_id=session_id` to the existing `Signals(...)` construction in `evaluate()` (it already has every other field on separate lines - add these two right after `engagement_event_id=engagement_event_id,`):

```python
        engagement_event_id=engagement_event_id,
        uid=uid,
        session_id=session_id,
```

Replace the hardcoded `recovery=None` call:

```python
    history = store.list_for_session(session_id)
    decision = _decider.decide(signals, history=history, recovery=None)
```

with:

```python
    history = store.list_for_session(session_id)
    last_decision_at = _last_decision_timestamp(history)
    recovery = (
        observed_recovery_since(uid, session_id, last_decision_at)
        if last_decision_at is not None
        else None
    )
    decision = _decider.decide(signals, history=history, recovery=recovery)
```

Add the small helper just above `evaluate()`:

```python
def _last_decision_timestamp(history: list):
    """When the most recent prior decision this session was made, or None
    if there isn't one yet. `history` is oldest-first (store.list_for_session's
    own contract)."""
    if not history:
        return None
    from app.analytics.domain.metrics import _parse_datetime

    return _parse_datetime(history[-1]["timestamp"])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_intervention_lifecycle.py -v -k "recovery_is_passed_to_the_decider or signals_carries_uid"`
Expected: PASS, both new tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS — `Signals`' two new fields have defaults, so no existing construction site breaks; `DefaultPolicy.decide()` already accepts and ignores `recovery`.

- [ ] **Step 6: Mutation check**

Temporarily change `if last_decision_at is not None` to `if False` (recovery always stays `None`, matching the pre-Task-2 behavior) and confirm `test_recovery_is_passed_to_the_decider_when_a_prior_decision_exists_this_session`'s second assertion (`assert seen[-1] is True`) fails. Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/intervention/decider.py backend/app/intervention/service.py backend/tests/test_intervention_lifecycle.py
```

---

### Task 3: `app/fusion/` package + `FusionSignals` dataclass

**Files:**
- Create: `backend/app/fusion/__init__.py`
- Create: `backend/app/fusion/signals.py`
- Test: `backend/tests/fusion/__init__.py`
- Test: `backend/tests/fusion/test_signals.py`

**Interfaces:**
- Produces: `FusionSignals` frozen dataclass with fields `engagement: Signals`, `recent_emotion_signals: list[str]`, `assistant_message_count_last_60s: int`, `recovery_since_last_decision: bool | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/fusion/__init__.py
```
(empty file, makes this a package so pytest discovers it the same way `backend/tests/analytics/` already does)

```python
# backend/tests/fusion/test_signals.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_signals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fusion'`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/fusion/__init__.py
"""
Module 6 — CV+AI Integration Layer (scope 6.6).

FusionPolicy (policy.py) is a second implementation of
app.intervention.decider.InterventionDecider, combining Module 3's camera
signals with Module 5's chat signals and live mid-session recovery
evidence (app.analytics.domain.metrics.observed_recovery_since, issue #45)
into sequenced intervention decisions.

Nothing in app/intervention/ is modified by this package's own logic (the
one exception - two additive fields on Signals - was made in Task 2, for
identity, not for fusion logic itself). Module 4's delivery code
(useIntervention.js, InterventionHost.jsx, the /intervention/* routes)
never needs to change: it already only knows how to render whatever
Decision the currently-active decider produced.

See docs/superpowers/specs/2026-09-30-module-6-fusion-design.md.
"""
```

```python
# backend/app/fusion/signals.py
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
    # output shape: "frustration" | "confusion" | "neutral".
    recent_emotion_signals: list[str]
    # "Did the learner ask for help through the panel?" - scope's own
    # framing: a struggling learner is the LEAST likely to ask, so silence
    # here is not reassuring on its own.
    assistant_message_count_last_60s: int
    # None means "no prior decision this session to measure recovery from
    # yet" - distinct from False ("measured, and no recovery observed").
    recovery_since_last_decision: bool | None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_signals.py -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS — new, unreferenced package.

- [ ] **Step 6: Mutation check**

Temporarily remove `frozen=True` from `@dataclass(frozen=True)` and confirm `test_is_frozen` fails (the assignment silently succeeds instead of raising `AttributeError`). Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/fusion/__init__.py backend/app/fusion/signals.py backend/tests/fusion/__init__.py backend/tests/fusion/test_signals.py
```

---

### Task 4: `build_fusion_signals` — the chat-history adapter

**Files:**
- Modify: `backend/app/fusion/signals.py`
- Test: `backend/tests/fusion/test_signals.py` (existing file from Task 3 — extend)

**Interfaces:**
- Consumes: `AssistantEventRepository` (`app/analytics/persistence/events.py`, existing), `Signals` (existing, carries `uid`/`session_id` as of Task 2).
- Produces: `build_fusion_signals(engagement_signals: Signals, *, recovery_since_last_decision: bool | None, now: datetime | None = None, window_seconds: float = 60.0, db=None) -> FusionSignals`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/fusion/test_signals.py`:

```python
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.fusion.signals import build_fusion_signals  # noqa: E402


class _FakeAssistantRepo:
    def __init__(self, events):
        self._events = events

    def list_by_session(self, session_id):
        return self._events


class _FakeDb:
    def __init__(self, repo):
        self._repo = repo

    def __getitem__(self, _name):
        return self._repo


def _learner_event(offset_seconds: int, learner_signal: str, now: datetime):
    return {
        "direction": "learner",
        "learner_signal": learner_signal,
        "timestamp": (now - timedelta(seconds=offset_seconds)).isoformat().replace("+00:00", "Z"),
    }


def test_build_fusion_signals_with_no_assistant_exchanges():
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=_FakeDb(_FakeAssistantRepo([])),
    )
    assert fs.recent_emotion_signals == []
    assert fs.assistant_message_count_last_60s == 0


def test_build_fusion_signals_counts_only_learner_direction_within_the_window():
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        _learner_event(10, "confusion", now),
        {**_learner_event(15, "neutral", now), "direction": "assistant"},  # not a learner turn
        _learner_event(90, "frustration", now),  # outside the 60s window
    ]
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=_FakeDb(_FakeAssistantRepo(events)),
    )
    assert fs.recent_emotion_signals == ["confusion"]
    assert fs.assistant_message_count_last_60s == 1


def test_build_fusion_signals_orders_emotion_signals_oldest_to_most_recent():
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        _learner_event(5, "frustration", now),
        _learner_event(45, "confusion", now),
    ]
    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=True,
        now=now,
        db=_FakeDb(_FakeAssistantRepo(events)),
    )
    assert fs.recent_emotion_signals == ["confusion", "frustration"]
    assert fs.recovery_since_last_decision is True


def test_build_fusion_signals_never_raises_when_the_repository_fails():
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    class BrokenRepo:
        def list_by_session(self, session_id):
            raise RuntimeError("db down")

    fs = build_fusion_signals(
        _engagement_signals(),
        recovery_since_last_decision=None,
        now=now,
        db=_FakeDb(BrokenRepo()),
    )
    assert fs.recent_emotion_signals == []
    assert fs.assistant_message_count_last_60s == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_signals.py -v -k build_fusion_signals`
Expected: FAIL — `ImportError: cannot import name 'build_fusion_signals'`.

- [ ] **Step 3: Write the implementation**

Add to `backend/app/fusion/signals.py`:

```python
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def build_fusion_signals(
    engagement_signals: Signals,
    *,
    recovery_since_last_decision: bool | None,
    now: datetime | None = None,
    window_seconds: float = 60.0,
    db=None,
) -> "FusionSignals":
    """Read this session's trailing assistant-chat window and combine it
    with the already-computed camera signals and recovery state.

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
                and (resolved_now - _parse_datetime(event["timestamp"])).total_seconds() <= window_seconds
            ]
            learner_turns.sort(key=lambda event: event["timestamp"])
            recent_emotion_signals = [event["learner_signal"] for event in learner_turns]
            message_count = len(learner_turns)
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_signals.py -v`
Expected: PASS, all 7 tests (3 from Task 3 + 4 new).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Mutation check**

Temporarily change `if event.get("direction") == "learner"` to `if True` (counts assistant turns too) and confirm `test_build_fusion_signals_counts_only_learner_direction_within_the_window` fails (`assistant_message_count_last_60s` becomes 2, not 1). Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/fusion/signals.py backend/tests/fusion/test_signals.py
```

---

### Task 5: `FusionWindow` — the 60-second gate

**Files:**
- Create: `backend/app/fusion/window.py`
- Test: `backend/tests/fusion/test_window.py`

**Interfaces:**
- Produces: `FusionWindow` class with `ready(uid: str, session_id: str, now: float) -> bool` and `mark_decided(uid: str, session_id: str, now: float) -> None`; module-level `FUSION_WINDOW_SECONDS = 60.0`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/fusion/test_window.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion.window import FUSION_WINDOW_SECONDS, FusionWindow  # noqa: E402


def test_a_never_seen_session_is_ready_immediately():
    """A session's first-ever fusion decision must not be blocked by a
    60-second wait that never had a previous decision to measure from."""
    window = FusionWindow()
    assert window.ready("u1", "s1", now=1000.0) is True


def test_not_ready_again_until_the_full_window_has_passed():
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u1", "s1", now=1000.0 + FUSION_WINDOW_SECONDS - 1) is False


def test_ready_again_once_the_window_has_fully_elapsed():
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u1", "s1", now=1000.0 + FUSION_WINDOW_SECONDS) is True


def test_sessions_are_tracked_independently():
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u1", "s2", now=1000.0) is True


def test_users_are_tracked_independently_even_with_the_same_session_id():
    """A defensive-but-real case: uid is part of the key, not just
    session_id, matching the (uid, session_id) keying convention already
    used by engagement/smoothing.py and intervention/cooldown.py."""
    window = FusionWindow()
    window.mark_decided("u1", "s1", now=1000.0)
    assert window.ready("u2", "s1", now=1000.0) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_window.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fusion.window'`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/fusion/window.py
"""
The "every 60 seconds" gate scope 6.6 asks for.

Not a new polling loop: Module 3 already calls in roughly every second via
/engagement/analyze. This is a pure, in-memory accumulator FusionPolicy
consults on every one of those calls - "has a full window passed since my
last actual decision for this session?" - matching the same
per-(uid, session_id), in-memory, dies-on-restart, single-worker-only
pattern already accepted and documented in engagement/smoothing.py and
intervention/cooldown.py. This is not a new limitation.
"""

FUSION_WINDOW_SECONDS = 60.0


class FusionWindow:
    def __init__(self) -> None:
        self._last_decided: dict[tuple[str, str], float] = {}

    def ready(self, uid: str, session_id: str, now: float) -> bool:
        last = self._last_decided.get((uid, session_id))
        if last is None:
            return True
        return now - last >= FUSION_WINDOW_SECONDS

    def mark_decided(self, uid: str, session_id: str, now: float) -> None:
        self._last_decided[(uid, session_id)] = now
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_window.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Mutation check**

Temporarily change `return now - last >= FUSION_WINDOW_SECONDS` to `return True` (always ready) and confirm `test_not_ready_again_until_the_full_window_has_passed` fails. Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/fusion/window.py backend/tests/fusion/test_window.py
```

---

### Task 6: `sequencing.py` — escalation-ladder bookkeeping

**Files:**
- Create: `backend/app/fusion/sequencing.py`
- Test: `backend/tests/fusion/test_sequencing.py`

**Interfaces:**
- Consumes: `Decision`, `SIMPLIFY_CONTENT`, `BULLET_SUMMARY`, `ASSISTANT_HELP_PROMPT` (`app/intervention/decider.py`, existing).
- Produces: `next_sequence(base_decision: Decision, *, history: list, recovery_since_last_decision: bool | None) -> Decision`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/fusion/test_sequencing.py
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.fusion.sequencing import next_sequence  # noqa: E402
from app.intervention.decider import (  # noqa: E402
    ASSISTANT_HELP_PROMPT,
    BULLET_SUMMARY,
    REASON_STRUGGLING,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    Decision,
)


def _decision(intervention_type: str) -> Decision:
    return Decision(
        intervention_type=intervention_type, reason_code=REASON_STRUGGLING,
        reason="test", tier=TIER_BROAD,
    )


def _history_entry(intervention_type: str, sequence_id: str | None = None, step_index: int | None = None):
    return {
        "intervention_type": intervention_type,
        "sequence_id": sequence_id,
        "step_index": step_index,
    }


def test_starts_a_fresh_sequence_when_there_is_no_history():
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=[], recovery_since_last_decision=None,
    )
    assert result.step_index == 0
    assert result.sequence_id is not None
    uuid.UUID(result.sequence_id)  # a real uuid4, not a placeholder string


def test_starts_a_fresh_sequence_after_genuine_recovery():
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=True,
    )
    assert result.sequence_id != "seq-1"
    assert result.step_index == 0


def test_escalates_when_the_same_type_would_repeat_without_recovery():
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=False,
    )
    assert result.sequence_id == "seq-1"
    assert result.step_index == 1
    assert result.intervention_type == BULLET_SUMMARY  # next rung up the ladder


def test_escalates_again_to_the_top_rung():
    history = [_history_entry(BULLET_SUMMARY, sequence_id="seq-1", step_index=1)]
    result = next_sequence(
        _decision(BULLET_SUMMARY), history=history, recovery_since_last_decision=False,
    )
    assert result.step_index == 2
    assert result.intervention_type == SIMPLIFY_CONTENT


def test_does_not_escalate_past_the_top_rung():
    history = [_history_entry(SIMPLIFY_CONTENT, sequence_id="seq-1", step_index=2)]
    result = next_sequence(
        _decision(SIMPLIFY_CONTENT), history=history, recovery_since_last_decision=False,
    )
    assert result.intervention_type == SIMPLIFY_CONTENT
    assert result.step_index == 3


def test_does_not_escalate_when_recovery_is_none():
    """Matches DefaultPolicy's own current, documented behavior: no
    escalation without a real recovery signal to escalate ON THE BASIS of -
    recovery=None is not the same as recovery=False."""
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=None,
    )
    assert result.sequence_id != "seq-1"
    assert result.step_index == 0


def test_does_not_escalate_when_the_base_decision_is_a_different_type():
    """Escalation only applies when the SAME type would repeat - a
    different type this time is already a different response, not a stall."""
    history = [_history_entry(ASSISTANT_HELP_PROMPT, sequence_id="seq-1", step_index=0)]
    result = next_sequence(
        _decision(BULLET_SUMMARY), history=history, recovery_since_last_decision=False,
    )
    assert result.sequence_id != "seq-1"
    assert result.step_index == 0


def test_tolerates_a_malformed_history_entry_missing_intervention_type():
    history = [{"sequence_id": "seq-1", "step_index": 0}]
    result = next_sequence(
        _decision(ASSISTANT_HELP_PROMPT), history=history, recovery_since_last_decision=False,
    )
    assert result.step_index == 0  # treated as "no comparable prior entry"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_sequencing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fusion.sequencing'`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/fusion/sequencing.py
"""
Decision.sequence_id / step_index bookkeeping (scope 6.6's "plans responses
in sequences rather than single isolated actions").

The ladder order mirrors DefaultPolicy's own tiers (policy.py), cheapest
first: assistant_help_prompt -> bullet_summary -> simplify_content. This is
NOT new escalation logic invented here - it is the same order DefaultPolicy
already uses to choose a type in the first place, now also used to choose
the NEXT type when the current one is about to repeat without the learner
having recovered. DefaultPolicy could not do this itself (policy.py's own
docstring: "it does not escalate... a fake escalation that never checks
whether the previous step worked would be worse than none") - recovery
only became checkable mid-session in Task 1/2 (issue #45).
"""

import uuid

from app.intervention.decider import ASSISTANT_HELP_PROMPT, BULLET_SUMMARY, SIMPLIFY_CONTENT, Decision

_LADDER = (ASSISTANT_HELP_PROMPT, BULLET_SUMMARY, SIMPLIFY_CONTENT)


def _next_rung(intervention_type: str) -> str:
    try:
        index = _LADDER.index(intervention_type)
    except ValueError:
        return intervention_type
    return _LADDER[min(index + 1, len(_LADDER) - 1)]


def _last_entry(history: list) -> dict | None:
    return history[-1] if history else None


def next_sequence(
    base_decision: Decision,
    *,
    history: list,
    recovery_since_last_decision: bool | None,
) -> Decision:
    """Return `base_decision` with sequence_id/step_index filled in -
    escalated one rung, continuing the previous sequence, if the same
    type would otherwise repeat without a genuine recovery in between.
    Starts a fresh sequence in every other case (no history, recovery was
    True, recovery is unknown/None, or this is already a different type
    than last time)."""
    last = _last_entry(history)
    last_type = last.get("intervention_type") if last else None
    should_escalate = (
        recovery_since_last_decision is False
        and last is not None
        and last_type == base_decision.intervention_type
    )

    if not should_escalate:
        return Decision(
            intervention_type=base_decision.intervention_type,
            reason_code=base_decision.reason_code,
            reason=base_decision.reason,
            tier=base_decision.tier,
            chunk_id=base_decision.chunk_id,
            content_id=base_decision.content_id,
            triggering_engagement_event_id=base_decision.triggering_engagement_event_id,
            sequence_id=str(uuid.uuid4()),
            step_index=0,
        )

    return Decision(
        intervention_type=_next_rung(base_decision.intervention_type),
        reason_code=base_decision.reason_code,
        reason=base_decision.reason,
        tier=base_decision.tier,
        chunk_id=base_decision.chunk_id,
        content_id=base_decision.content_id,
        triggering_engagement_event_id=base_decision.triggering_engagement_event_id,
        sequence_id=last["sequence_id"],
        step_index=(last.get("step_index") or 0) + 1,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_sequencing.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Mutation check**

Temporarily change `recovery_since_last_decision is False` to `recovery_since_last_decision is not True` (treats `None` the same as `False`) and confirm `test_does_not_escalate_when_recovery_is_none` fails. Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/fusion/sequencing.py backend/tests/fusion/test_sequencing.py
```

---

### Task 7: `FusionPolicy` — the decider itself

**Files:**
- Create: `backend/app/fusion/policy.py`
- Test: `backend/tests/fusion/test_policy.py`

**Interfaces:**
- Consumes: `FusionSignals`, `build_fusion_signals` (Task 3/4), `FusionWindow` (Task 5), `next_sequence` (Task 6), `DefaultPolicy` (`app/intervention/policy.py`, existing), `InterventionDecider` Protocol (`app/intervention/decider.py`, existing).
- Produces: `FusionPolicy` class satisfying `InterventionDecider` (`policy_version: str`, `decide(signals, *, history, recovery=None) -> Decision | None`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/fusion/test_policy.py
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


def test_policy_version_is_set():
    assert FusionPolicy().policy_version == "v1-fusion"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fusion.policy'`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/fusion/policy.py
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
                if not bypasses_window:
                    self._window.mark_decided(uid, session_id, now)
                return None

        decision = next_sequence(
            base_decision,
            history=history,
            recovery_since_last_decision=fusion_signals.recovery_since_last_decision,
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/fusion/test_policy.py -v`
Expected: PASS, all 9 tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Mutation check**

Temporarily change `if confused_or_frustrated < CHAT_CORROBORATION_COUNT or already_asked:` to `if already_asked:` (drops the corroboration-count requirement) and confirm `test_chat_does_not_trigger_on_a_single_confused_turn` fails. Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/fusion/policy.py backend/tests/fusion/test_policy.py
```

---

### Task 8: Feature-flagged wiring

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_main_fusion_wiring.py`

**Interfaces:**
- Consumes: `FusionPolicy` (Task 7), `service.set_decider`/`service.get_decider` (`app/intervention/service.py`, existing).
- Produces: nothing new consumed elsewhere — this is the terminal wiring task.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_main_fusion_wiring.py
"""
The feature flag that turns Module 6 on. Off by default - a policy that
has never run against a live session should not become everyone's
default the moment it merges (same reasoning ml/inference/model.py uses
for why the calibrated model pair only activates for a learner who has
actually calibrated).
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.intervention import service  # noqa: E402
from app.intervention.policy import DefaultPolicy  # noqa: E402


def _reload_main():
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    else:
        importlib.import_module("app.main")


def test_default_policy_is_used_when_the_flag_is_unset(monkeypatch):
    monkeypatch.delenv("ADAPTLY_FUSION_POLICY", raising=False)
    service.set_decider(DefaultPolicy())  # known starting state
    _reload_main()
    assert isinstance(service.get_decider(), DefaultPolicy)


def test_fusion_policy_is_used_when_the_flag_is_set(monkeypatch):
    from app.fusion.policy import FusionPolicy

    monkeypatch.setenv("ADAPTLY_FUSION_POLICY", "1")
    service.set_decider(DefaultPolicy())  # known starting state
    _reload_main()
    assert isinstance(service.get_decider(), FusionPolicy)
    # Cleanup: leave the global decider as DefaultPolicy for every other
    # test file in the same process, and re-import app.main with the flag
    # unset again so later test files see the default wiring.
    service.set_decider(DefaultPolicy())
    monkeypatch.delenv("ADAPTLY_FUSION_POLICY", raising=False)
    _reload_main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_main_fusion_wiring.py -v`
Expected: FAIL — `test_fusion_policy_is_used_when_the_flag_is_set` fails because setting the env var and reloading `app.main` has no effect yet (`service.get_decider()` stays a `DefaultPolicy`).

- [ ] **Step 3: Write the implementation**

In `backend/app/main.py`, add after the existing imports:

```python
import os

from app.intervention import service as intervention_service
```

Add after `app.include_router(api_router)`:

```python
# Module 6 (scope 6.6) - off by default. A policy that has never run
# against a live session should not become everyone's default the moment
# it merges; see app/fusion/policy.py's own module docstring for why its
# one new judgement call (chat as a tie-breaker, never an independent
# trigger for the intrusive interventions) is deliberately conservative
# rather than claimed as measured.
if os.getenv("ADAPTLY_FUSION_POLICY") == "1":
    from app.fusion.policy import FusionPolicy

    intervention_service.set_decider(FusionPolicy())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_main_fusion_wiring.py -v`
Expected: PASS, both tests.

- [ ] **Step 5: Run the pinned integration test and the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_intervention_lifecycle.py -v -k test_module_6_can_replace_the_policy_without_touching_delivery`
Expected: PASS — unmodified; this task proves Module 6's own real decider satisfies the same promise the stub in that test already pins.

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS, full suite. Note: because `service.set_decider(...)` mutates shared module state, run the full suite (not just this file) to confirm no test-ordering leakage between `test_main_fusion_wiring.py` and any other file that assumes `DefaultPolicy` is active — `test_module_6_can_replace_the_policy_without_touching_delivery` (existing) already calls `service.set_decider(AlwaysBreak())` without restoring it afterward, so this is a pre-existing pattern in this codebase, not a new risk introduced here; if ordering trouble does appear, add a `fake_store`-style autouse fixture resetting the decider to `DefaultPolicy()` in `test_main_fusion_wiring.py`'s own file and record that as a ledger Ruling.

- [ ] **Step 6: Mutation check**

Temporarily change `if os.getenv("ADAPTLY_FUSION_POLICY") == "1":` to `if False:` and confirm `test_fusion_policy_is_used_when_the_flag_is_set` fails. Restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/main.py backend/tests/test_main_fusion_wiring.py
```

---

## Final full-suite check

- [ ] **Backend:** `cd backend && .venv/Scripts/python.exe -m pytest -q` — expect all prior tests plus this plan's new tests passing, 0 failures.
- [ ] No frontend changes in this plan — `npx vitest run` is not expected to differ from its current passing state, but running it once at the end costs little and confirms nothing was accidentally touched.

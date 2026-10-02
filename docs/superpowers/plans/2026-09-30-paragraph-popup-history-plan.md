# Paragraph Focus Highlight + Anchored Intervention Popup + Persistent History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show which paragraph the fusion system is confident about (a quiet
highlight), redeliver Module 4's auto-triggered interventions as a popup
anchored beside that paragraph with a paragraph-identity lifecycle instead of
a fixed timer, and give the assistant a real, persistent, site-agnostic
conversation history instead of client-only state that resets on every
remount.

**Architecture:** Frontend: a highlight prop threaded through the existing
`ContentViewer`/`ContentChunk`; two new small hooks
(`useAnchoredPosition`, `useParagraphPopup`) composed on top of the
*existing*, unmodified `useIntervention`; a new `ParagraphPopup` component
reusing `InterventionHost`'s existing `GeneratedText` rendering. Backend: one
new fail-silent store module (`history_store.py`, mirrors
`intervention/store.py`'s own pattern exactly) backing one new `GET
/assistant/history` endpoint, plus two additive write-sites on endpoints that
already exist.

**Tech Stack:** React 18 hooks, vitest/Testing Library (frontend); FastAPI,
pytest (backend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-paragraph-popup-history-design.md`

## Global Constraints

- `HIGHLIGHT_CONFIDENCE_THRESHOLD = 0.3` (estimate, matches the order of the
  existing `SCATTERED_CONFIDENCE_THRESHOLD`), `PARAGRAPH_CHANGE_CONFIRM_MS = 3000`
  (estimate, flicker guard) — copied verbatim from the spec.
- **The popup's auto-close condition is paragraph-identity (`chunk_id`
  equality), never a fixed timer on its own.** This is the spec's central
  finding (section 2) — do not reintroduce word/line-level tracking or a
  fixed display duration.
- **`useDwellFusion.js` and `fusionScoring.js` are not modified in this
  plan.** Every task only *consumes* `activeChunkId`/`fusionConfidence`.
- **No score, percentage, or confidence value is ever rendered to the
  learner** (scope 6.8) — the highlight is a CSS class, nothing textual.
- Site-wide assistant availability is explicitly out of scope (the user
  declined it) — the sticky `AssistantPanel` stays mounted exactly where it
  is today (`StudySession.jsx`, gated by `started`); only its history-loading
  behavior changes.
- **Do not run `git commit`.** Stage changes (`git add`) at the end of each
  task and stop there — commits happen only when the user says the whole
  feature is done. Do not touch `backend/.venv`, `frontend/node_modules`, or
  `sibtain-workspace/.venv-ml`.
- Mutation-test every new behavior: after a step's test passes, briefly break
  the implementation on purpose and confirm the test catches it, then
  restore — this project's established practice.
- Assistant history is written on a **successful** exchange only (an error
  response records nothing new in `assistant_messages`, matching how
  `analytics_sink`'s existing error-path calls already record only
  `status="error"` diagnostics, not a fabricated turn) — the spec is silent
  on this edge case; this is the plan's explicit resolution of that
  ambiguity.

## Review Focus

- A learner who dismisses the popup, then a **new** intervention fires for a
  **different** paragraph moments later — the new popup must anchor to the
  new paragraph's element, not the dismissed one's stale position.
- The popup's paragraph confirms a change (3s elapsed) at the exact instant
  the learner scrolls back to it — the cancel-on-return path must win a
  same-tick race, never close-then-immediately-reopen.
- `GET /assistant/history` called by a learner with **no** history yet
  (brand new account) — must return an empty list, not a 404 or an error.
- The backend history write inside `GET /intervention/{id}/content` must
  never turn a working content-generation call into a failure if the
  history write itself throws (e.g. a transient Mongo error).
- A popup anchored to a paragraph that scrolls **entirely out of the
  viewport** (not just to a different chunk) — `useAnchoredPosition` must
  keep returning a (now off-screen) rect rather than crashing on a detached
  element, and the paragraph-identity lifecycle (not visibility) still
  governs whether it closes.

---

## File Structure

```
backend/app/ai_assistant/
  history_store.py       NEW — fail-silent assistant_messages store
  schemas.py              MODIFY — HistoryMessage/HistoryResponse, AssistantMessageRequest.source
  api.py                  MODIFY — GET /assistant/history, POST /assistant/messages writes history

backend/app/intervention/
  routes.py                MODIFY — GET /{id}/content writes an assistant-role history turn

backend/tests/
  test_assistant_history_store.py  NEW
  test_assistant_history_api.py    NEW
  test_intervention_content_history.py  NEW

frontend/src/content/
  ContentViewer.jsx        MODIFY — isFocused prop/highlight class

frontend/src/intervention/
  useAnchoredPosition.js       NEW
  useAnchoredPosition.test.js  NEW
  useParagraphPopup.js         NEW
  useParagraphPopup.test.js    NEW
  ParagraphPopup.jsx           NEW
  ParagraphPopup.test.jsx      NEW
  InterventionHost.jsx         MODIFY — export GeneratedText

frontend/src/features/ai-assistant/
  assistantApi.js           MODIFY — fetchAssistantHistory
  AssistantPanel.jsx         MODIFY — loads history on mount

frontend/src/pages/
  StudySession.jsx          MODIFY — highlight props to ContentViewer, ParagraphPopup replaces
                             the bottom-of-page InterventionHost render, chunk-element
                             bookkeeping for anchoring
```

---

### Task 1: Backend — `assistant_messages` history store

**Files:**
- Create: `backend/app/ai_assistant/history_store.py`
- Test: `backend/tests/test_assistant_history_store.py`

**Interfaces:**
- Produces: `insert_message(*, uid, role, content, source, trigger=None, content_id=None, chunk_id=None, session_id=None) -> bool`, `list_messages(uid, limit=50, before=None) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_assistant_history_store.py
import time

from app.ai_assistant import history_store


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction):
        self._docs = sorted(self._docs, key=lambda d: d[field], reverse=direction < 0)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.fail = False

    def insert_one(self, document):
        if self.fail:
            raise RuntimeError("no connection")
        self.docs.append(dict(document))

    def find(self, query):
        if self.fail:
            raise RuntimeError("no connection")
        matched = [d for d in self.docs if d["uid"] == query["uid"]]
        if "timestamp" in query:
            matched = [d for d in matched if d["timestamp"] < query["timestamp"]["$lt"]]
        return FakeCursor(matched)


class FakeDB:
    def __init__(self):
        self.assistant_messages = FakeCollection()


def test_insert_then_list_round_trips(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    assert history_store.insert_message(uid="u1", role="user", content="hi", source="panel")
    result = history_store.list_messages("u1")
    assert len(result) == 1
    assert result[0]["content"] == "hi"


def test_list_is_newest_first(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    history_store.insert_message(uid="u1", role="user", content="first", source="panel")
    history_store.insert_message(uid="u1", role="assistant", content="second", source="panel")
    result = history_store.list_messages("u1")
    assert [m["content"] for m in result] == ["second", "first"]


def test_one_learner_never_sees_anothers_history(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    history_store.insert_message(uid="u1", role="user", content="mine", source="panel")
    history_store.insert_message(uid="u2", role="user", content="theirs", source="panel")
    result = history_store.list_messages("u1")
    assert [m["content"] for m in result] == ["mine"]


def test_a_brand_new_learner_has_an_empty_history(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)
    assert history_store.list_messages("nobody-yet") == []


def test_pagination_uses_before_as_an_exclusive_upper_bound(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    history_store.insert_message(uid="u1", role="user", content="old", source="panel")
    time.sleep(0.001)
    cutoff = time.time()
    time.sleep(0.001)
    history_store.insert_message(uid="u1", role="user", content="new", source="panel")

    result = history_store.list_messages("u1", before=cutoff)
    assert [m["content"] for m in result] == ["old"]


def test_a_database_problem_on_insert_is_reported_not_raised(monkeypatch):
    fake = FakeDB()
    fake.assistant_messages.fail = True
    monkeypatch.setattr(history_store, "db", fake)
    assert history_store.insert_message(uid="u1", role="user", content="x", source="panel") is False


def test_a_database_problem_on_list_returns_empty_not_raised(monkeypatch):
    fake = FakeDB()
    fake.assistant_messages.fail = True
    monkeypatch.setattr(history_store, "db", fake)
    assert history_store.list_messages("u1") == []


def test_optional_context_fields_default_to_none(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)
    history_store.insert_message(uid="u1", role="assistant", content="x", source="popup")
    stored = history_store.list_messages("u1")[0]
    assert stored["trigger"] is None
    assert stored["content_id"] is None
    assert stored["chunk_id"] is None
    assert stored["session_id"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_assistant_history_store.py -v`
Expected: FAIL — `app.ai_assistant.history_store` does not exist.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/ai_assistant/history_store.py
"""
Fail-silent store for the learner's persistent assistant conversation.

Same contract as app/intervention/store.py: a database problem must never
turn a successful assistant answer, or a successful content generation,
into an error response - every function here returns rather than raises.

uid-keyed, not session_id-keyed: the design is one continuous conversation
per learner (confirmed 2026-09-30), not one per study session. session_id/
content_id/chunk_id are recorded on each turn for context, not as the
partition key.
"""

import logging
import time
import uuid

from app.core.db import db

log = logging.getLogger(__name__)


def insert_message(
    *,
    uid: str,
    role: str,
    content: str,
    source: str,
    trigger: str | None = None,
    content_id: str | None = None,
    chunk_id: str | None = None,
    session_id: str | None = None,
) -> bool:
    """Append one turn. Returns whether it was stored."""
    document = {
        "_id": str(uuid.uuid4()),
        "uid": uid,
        "timestamp": time.time(),
        "role": role,
        "content": content,
        "source": source,
        "trigger": trigger,
        "content_id": content_id,
        "chunk_id": chunk_id,
        "session_id": session_id,
    }
    try:
        db.assistant_messages.insert_one(document)
        return True
    except Exception:
        log.warning("assistant message for %s could not be stored", uid, exc_info=True)
        return False


def list_messages(uid: str, limit: int = 50, before: float | None = None) -> list[dict]:
    """This learner's own history, newest first. before is an exclusive
    upper bound on timestamp, for paging further back."""
    query: dict = {"uid": uid}
    if before is not None:
        query["timestamp"] = {"$lt": before}
    try:
        cursor = db.assistant_messages.find(query).sort("timestamp", -1).limit(limit)
        return list(cursor)
    except Exception:
        log.warning("assistant history for %s could not be read", uid, exc_info=True)
        return []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_assistant_history_store.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Mutation check**

Temporarily remove the `try`/`except` around `db.assistant_messages.insert_one`
in `insert_message` (let it raise directly) and confirm
`test_a_database_problem_on_insert_is_reported_not_raised` fails (raises
instead of returning `False`); restore.

- [ ] **Step 6: Stage for review**

```bash
git add backend/app/ai_assistant/history_store.py backend/tests/test_assistant_history_store.py
```

---

### Task 2: Backend — `GET /assistant/history` endpoint

**Files:**
- Modify: `backend/app/ai_assistant/schemas.py`
- Modify: `backend/app/ai_assistant/api.py`
- Test: `backend/tests/test_assistant_history_api.py`

**Interfaces:**
- Consumes: `history_store.list_messages` (Task 1).
- Produces: `GET /assistant/history?limit=&before=` returning
  `{"messages": [{id, role, content, source, trigger, content_id, chunk_id, session_id, timestamp}, ...]}`,
  newest first.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_assistant_history_api.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai_assistant import history_store  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    app.dependency_overrides[get_current_user] = lambda: {"uid": "u1", "email": "u1@t.com"}
    yield
    app.dependency_overrides.clear()


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction):
        self._docs = sorted(self._docs, key=lambda d: d[field], reverse=direction < 0)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, document):
        self.docs.append(dict(document))

    def find(self, query):
        return FakeCursor([d for d in self.docs if d["uid"] == query["uid"]])


@pytest.fixture
def fake_history(monkeypatch):
    class FakeDB:
        assistant_messages = FakeCollection()

    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)
    return fake.assistant_messages


def test_a_new_learner_gets_an_empty_history(fake_history):
    response = client.get("/assistant/history")
    assert response.status_code == 200
    assert response.json() == {"messages": []}


def test_returns_stored_turns_newest_first(fake_history):
    history_store.insert_message(uid="u1", role="user", content="q1", source="panel")
    history_store.insert_message(uid="u1", role="assistant", content="a1", source="panel")
    response = client.get("/assistant/history")
    contents = [m["content"] for m in response.json()["messages"]]
    assert contents == ["a1", "q1"]


def test_never_returns_another_learners_history(fake_history):
    history_store.insert_message(uid="u2", role="user", content="not mine", source="panel")
    response = client.get("/assistant/history")
    assert response.json()["messages"] == []


def test_requires_authentication():
    app.dependency_overrides.clear()
    assert client.get("/assistant/history").status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_assistant_history_api.py -v`
Expected: FAIL — `GET /assistant/history` does not exist (404).

- [ ] **Step 3: Add the schemas**

In `backend/app/ai_assistant/schemas.py`, add:

```python
MAX_HISTORY_LIMIT = 100


class HistoryMessage(AssistantModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    source: Literal["panel", "popup"]
    trigger: str | None = None
    content_id: str | None = None
    chunk_id: str | None = None
    session_id: str | None = None
    timestamp: float


class HistoryResponse(AssistantModel):
    messages: list[HistoryMessage]
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/ai_assistant/api.py`, add the import and route:

```python
from app.ai_assistant import history_store
from app.ai_assistant.schemas import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    HistoryResponse,
    HistoryMessage,
    MAX_HISTORY_LIMIT,
    SuggestionsRequest,
    SuggestionsResponse,
)
```

```python
@router.get("/history", response_model=HistoryResponse)
def get_history(
    limit: int = 50,
    before: float | None = None,
    user: dict = Depends(get_current_user),
) -> HistoryResponse:
    """The learner's own persistent assistant conversation, newest first."""
    bounded_limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    raw = history_store.list_messages(user["uid"], limit=bounded_limit, before=before)
    return HistoryResponse(
        messages=[
            HistoryMessage(
                id=doc["_id"],
                role=doc["role"],
                content=doc["content"],
                source=doc["source"],
                trigger=doc.get("trigger"),
                content_id=doc.get("content_id"),
                chunk_id=doc.get("chunk_id"),
                session_id=doc.get("session_id"),
                timestamp=doc["timestamp"],
            )
            for doc in raw
        ]
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_assistant_history_api.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 6: Mutation check**

Temporarily remove the `user["uid"]` filter effect by changing
`history_store.list_messages(user["uid"], ...)` to
`history_store.list_messages("u2", ...)` and confirm
`test_never_returns_another_learners_history` fails (now returns u2's data
matching itself, which the test would catch since it inserts under u2 and
expects empty back for u1's request context — verify by running); restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/ai_assistant/schemas.py backend/app/ai_assistant/api.py backend/tests/test_assistant_history_api.py
```

---

### Task 3: Backend — `POST /assistant/messages` writes history

**Files:**
- Modify: `backend/app/ai_assistant/schemas.py`
- Modify: `backend/app/ai_assistant/api.py`
- Test: `backend/tests/test_assistant_history_api.py` (extend)

**Interfaces:**
- Consumes: `history_store.insert_message` (Task 1).
- Produces: `AssistantMessageRequest.source: Literal["panel", "popup"] = "panel"` (additive field).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_assistant_history_api.py`:

```python
from unittest.mock import patch

from app.ai_assistant import service


def _stub_response():
    from app.ai_assistant.schemas import AssistantMessageResponse

    return (
        AssistantMessageResponse(
            answer="A plain answer.",
            suggested_questions=["Q1?", "Q2?", "Q3?"],
            emotion_signal="neutral",
            used_context=True,
            response_mode="text",
            session_id="s1",
            content_id="c1",
            chunk_id="0",
        ),
        "mock-model",
    )


def test_a_successful_exchange_is_recorded_in_history(fake_history):
    with patch.object(service, "create_assistant_response", return_value=_stub_response()):
        client.post(
            "/assistant/messages",
            json={
                "question": "What does this mean?",
                "session_id": "s1",
                "content_id": "c1",
                "current_chunk": {"chunk_id": "0", "text": "Some passage."},
            },
        )
    contents = [m["content"] for m in client.get("/assistant/history").json()["messages"]]
    assert "A plain answer." in contents
    assert "What does this mean?" in contents


def test_source_defaults_to_panel_and_is_recorded(fake_history):
    with patch.object(service, "create_assistant_response", return_value=_stub_response()):
        client.post(
            "/assistant/messages",
            json={
                "question": "Q",
                "session_id": "s1",
                "content_id": "c1",
                "current_chunk": {"chunk_id": "0", "text": "Some passage."},
            },
        )
    messages = client.get("/assistant/history").json()["messages"]
    assert all(m["source"] == "panel" for m in messages)


def test_popup_source_is_recorded_when_sent(fake_history):
    with patch.object(service, "create_assistant_response", return_value=_stub_response()):
        client.post(
            "/assistant/messages",
            json={
                "question": "Q",
                "session_id": "s1",
                "content_id": "c1",
                "current_chunk": {"chunk_id": "0", "text": "Some passage."},
                "source": "popup",
            },
        )
    messages = client.get("/assistant/history").json()["messages"]
    assert all(m["source"] == "popup" for m in messages)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_assistant_history_api.py -v`
Expected: FAIL — `source` field rejected (`extra="forbid"` on `AssistantModel`)
and no history is written yet.

- [ ] **Step 3: Add the field and the write**

In `backend/app/ai_assistant/schemas.py`, add to `AssistantMessageRequest`
(after `input_mode`):

```python
    # Where this question originated - the sticky panel, or the anchored
    # paragraph popup's own inline follow-up composer. Additive; existing
    # callers that never send it default to "panel", today's only source.
    source: Literal["panel", "popup"] = "panel"
```

In `backend/app/ai_assistant/api.py`, after the successful response (before
`return response`) in `create_assistant_message`:

```python
    history_store.insert_message(
        uid=user["uid"],
        role="user",
        content=request.question,
        source=request.source,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
        session_id=request.session_id,
    )
    history_store.insert_message(
        uid=user["uid"],
        role="assistant",
        content=response.answer,
        source=request.source,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
        session_id=request.session_id,
    )
```

(Both calls are already fail-silent per Task 1 — no additional try/except
needed at this call site.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_assistant_history_api.py -v`
Expected: PASS, all 7 tests (4 from Task 2 + 3 new).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS — no existing test asserted anything about `AssistantMessageRequest`
rejecting unknown fields in a way this additive, defaulted field would break
(`extra="forbid"` only rejects fields NOT declared on the model; `source` is
now declared).

- [ ] **Step 6: Mutation check**

Temporarily delete both `history_store.insert_message(...)` calls and
confirm `test_a_successful_exchange_is_recorded_in_history` fails (history
stays empty); restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/ai_assistant/schemas.py backend/app/ai_assistant/api.py backend/tests/test_assistant_history_api.py
```

---

### Task 4: Backend — `GET /intervention/{id}/content` writes an assistant-role history turn

**Files:**
- Modify: `backend/app/intervention/routes.py`
- Test: `backend/tests/test_intervention_content_history.py`

**Interfaces:**
- Consumes: `history_store.insert_message` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_intervention_content_history.py
"""
The popup's auto-triggered content (simplify_content/bullet_summary) must
land in the same persistent history the sticky panel reads, tagged
source="popup" so it renders distinguishably later - without needing the
frontend to remember to call anything separately.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai_assistant import history_store  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.intervention import provider, simplify, store  # noqa: E402
from app.intervention.decider import SIMPLIFY_CONTENT, TIER_BROAD, Decision  # noqa: E402
from app.intervention import contracts  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

PASSAGE = "A passage long enough to be worth rewriting, several sentences of it here."


class FakeAssistantCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, document):
        self.docs.append(dict(document))

    def find(self, query):
        matched = [d for d in self.docs if d["uid"] == query["uid"]]

        class Cursor:
            def sort(self, *a):
                return self

            def limit(self, *a):
                return self

            def __iter__(self):
                return iter(matched)

        return Cursor()


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {"uid": "u1", "email": "u1@t.com"}

    class FakeAssistantDB:
        assistant_messages = FakeAssistantCollection()

    monkeypatch.setattr(history_store, "db", FakeAssistantDB())
    yield
    app.dependency_overrides.clear()


def _stored_event(chunk_id="7", content_id="c1"):
    decision = Decision(
        intervention_type=SIMPLIFY_CONTENT,
        reason_code="struggling",
        reason="Signs of difficulty.",
        tier=TIER_BROAD,
        chunk_id=chunk_id,
        content_id=content_id,
    )
    event = contracts.build_intervention_event(
        decision=decision, user_id="u1", session_id="s1",
        triggering_engagement_state="struggling", policy_version="v1-tiered",
    )
    store.save(event)
    return event


def test_a_successful_generation_is_recorded_as_a_popup_turn(monkeypatch):
    event = _stored_event()
    monkeypatch.setattr(
        simplify, "for_intervention",
        lambda uid, ev: {
            "chunk_id": ev["chunk_id"], "original": PASSAGE,
            "generated": "A simpler version.", "generator": "stub", "cached": False,
        },
    )
    client.get(f"/intervention/{event['intervention_id']}/content")

    from app.ai_assistant import api as assistant_api  # noqa: E402  (avoid unused-import lint elsewhere)
    app.dependency_overrides[get_current_user] = lambda: {"uid": "u1", "email": "u1@t.com"}
    history = client.get("/assistant/history").json()["messages"]
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "A simpler version."
    assert history[0]["source"] == "popup"
    assert history[0]["trigger"] == SIMPLIFY_CONTENT
    assert history[0]["chunk_id"] == "7"
    assert history[0]["content_id"] == "c1"


def test_a_failed_generation_records_nothing(monkeypatch):
    event = _stored_event()
    monkeypatch.setattr(
        simplify, "for_intervention",
        lambda uid, ev: (_ for _ in ()).throw(provider.GenerationUnavailable("no model")),
    )
    client.get(f"/intervention/{event['intervention_id']}/content")
    history = client.get("/assistant/history").json()["messages"]
    assert history == []


def test_a_history_write_failure_does_not_break_a_successful_generation(monkeypatch):
    event = _stored_event()
    monkeypatch.setattr(
        simplify, "for_intervention",
        lambda uid, ev: {
            "chunk_id": ev["chunk_id"], "original": PASSAGE,
            "generated": "A simpler version.", "generator": "stub", "cached": False,
        },
    )
    monkeypatch.setattr(history_store, "insert_message", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))
    response = client.get(f"/intervention/{event['intervention_id']}/content")
    assert response.status_code == 200
    assert response.json()["generated"] == "A simpler version."
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_intervention_content_history.py -v`
Expected: FAIL — first test finds an empty history (nothing written yet);
third test fails because `history_store.insert_message` isn't called at all
yet inside the content endpoint, so the monkeypatched exception never fires
and the assertion trivially passes for the wrong reason — re-examine after
Step 3 that this test is exercising the real path, not passing vacuously
(see Step 4's note).

- [ ] **Step 3: Add the write**

In `backend/app/intervention/routes.py`, add the import:

```python
from app.ai_assistant import history_store
```

Replace the `return { ... }` at the end of `intervention_content` (after the
existing `result = simplify.for_intervention(...)` success path, before the
final `return`) with:

```python
    history_store.insert_message(
        uid=user["uid"],
        role="assistant",
        content=result["generated"],
        source="popup",
        trigger=event["intervention_type"],
        content_id=event.get("content_id"),
        chunk_id=result["chunk_id"],
        session_id=event.get("session_id"),
    )

    return {
        "intervention_id": intervention_id,
        "intervention_type": event["intervention_type"],
        "chunk_id": result["chunk_id"],
        "original": result["original"],
        "generated": result["generated"],
        "generator": result["generator"],
        "cached": result["cached"],
    }
```

(`history_store.insert_message` is already fail-silent per Task 1 — no
additional try/except needed here, which is exactly what Step 3's third test
proves.)

- [ ] **Step 4: Run the tests to verify they pass, and confirm the third test is a real proof**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_intervention_content_history.py -v`
Expected: PASS, all 3 tests. Confirm the third test is real (not vacuously
passing) by temporarily removing the `monkeypatch.setattr(history_store,
"insert_message", ...)` line from that test and re-running just that test -
it must still pass (200, correct body) either way, but re-adding the
monkeypatch and checking the endpoint doesn't 500 is what proves the
try/except-free fail-silent contract actually holds under a raising
dependency.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS — the existing `test_intervention_content.py` suite (Module 4
P3) is unaffected, since the new write is purely additive and fail-silent.

- [ ] **Step 6: Mutation check**

Temporarily comment out the `history_store.insert_message(...)` call added
in Step 3 and confirm `test_a_successful_generation_is_recorded_as_a_popup_turn`
fails (empty history); restore.

- [ ] **Step 7: Stage for review**

```bash
git add backend/app/intervention/routes.py backend/tests/test_intervention_content_history.py
```

---

### Task 5: Frontend — paragraph focus highlight

**Files:**
- Modify: `frontend/src/content/ContentViewer.jsx`
- Modify: `frontend/src/content/ContentViewer.test.jsx` (existing file — extend)
- Modify: `frontend/src/pages/StudySession.jsx`

**Interfaces:**
- Consumes: `activeChunkId`, `fusionConfidence` (already returned by
  `useDwellFusion`, unmodified).
- Produces: `ContentViewer` gains two new optional props,
  `activeChunkId: string|null` and `fusionConfidence: number = 0`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/content/ContentViewer.test.jsx` (existing file — follow
its existing render-with-a-two-chunk-document pattern):

```javascript
  it("highlights the chunk that matches activeChunkId when confidence clears the threshold", () => {
    render(
      <ContentViewer
        content={twoChunkDocument}
        activeChunkId="0"
        fusionConfidence={0.5}
      />
    );
    const focused = screen.getByText(twoChunkDocument.chunks[0].text).closest("section");
    const other = screen.getByText(twoChunkDocument.chunks[1].text).closest("section");
    expect(focused.className).toMatch(/bg-accent/);
    expect(other.className).not.toMatch(/bg-accent/);
  });

  it("does not highlight anything when confidence is below the threshold", () => {
    render(
      <ContentViewer
        content={twoChunkDocument}
        activeChunkId="0"
        fusionConfidence={0.1}
      />
    );
    const focused = screen.getByText(twoChunkDocument.chunks[0].text).closest("section");
    expect(focused.className).not.toMatch(/bg-accent/);
  });

  it("does not highlight anything when activeChunkId is null", () => {
    render(<ContentViewer content={twoChunkDocument} activeChunkId={null} fusionConfidence={0.9} />);
    const first = screen.getByText(twoChunkDocument.chunks[0].text).closest("section");
    expect(first.className).not.toMatch(/bg-accent/);
  });
```

(If this test file's existing fixture for a two-chunk document has a
different name than `twoChunkDocument`, use its actual existing fixture -
this file already renders multi-chunk documents for its current 10 tests.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/content/ContentViewer.test.jsx`
Expected: FAIL — 3 new tests fail (`className` never matches `/bg-accent/`,
since the prop does not exist yet).

- [ ] **Step 3: Implement the highlight**

In `frontend/src/content/ContentViewer.jsx`, add near the top:

```javascript
const HIGHLIGHT_CONFIDENCE_THRESHOLD = 0.3;
```

Change the `ContentChunk` function signature and its `<section>`:

```javascript
function ContentChunk({ chunk, onChunkRef, isFocused }) {
  const ref = useCallback(
    (element) => {
      if (onChunkRef) onChunkRef(chunk.chunk_id, element);
    },
    [onChunkRef, chunk.chunk_id]
  );

  return (
    <section
      ref={ref}
      data-chunk-id={chunk.chunk_id}
      className={isFocused ? "bg-accent/10 rounded-md" : undefined}
      style={{ marginBottom: "1.75rem", transition: "background-color 300ms ease" }}
    >
```

(Leave the rest of `ContentChunk`'s body - the `section_title`/`text`
rendering - unchanged.)

Change the exported component's signature and chunk-mapping:

```javascript
export default function ContentViewer({
  content,
  onChunkRef,
  lineSpacing = 1.7,
  activeChunkId = null,
  fusionConfidence = 0,
}) {
```

```javascript
          {ordered.map((chunk) => (
            <ContentChunk
              key={chunk.chunk_id}
              chunk={chunk}
              onChunkRef={onChunkRef}
              isFocused={
                chunk.chunk_id === activeChunkId
                && fusionConfidence >= HIGHLIGHT_CONFIDENCE_THRESHOLD
              }
            />
          ))}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/content/ContentViewer.test.jsx`
Expected: PASS, all 13 tests (10 existing + 3 new).

- [ ] **Step 5: Wire it in `StudySession.jsx`**

Change the existing `<ContentViewer content={document_.content} onChunkRef={dwell.register} />`
(the line already identified at `StudySession.jsx:399`) to:

```jsx
              <ContentViewer
                content={document_.content}
                onChunkRef={dwell.register}
                activeChunkId={dwell.activeChunkId}
                fusionConfidence={dwell.fusionConfidence}
              />
```

- [ ] **Step 6: Run the existing StudySession suite to confirm no regression**

Run: `cd frontend && npx vitest run src/pages/StudySession.chunkWiring.test.jsx src/pages/StudySession.test.jsx`
Expected: PASS, unchanged - these mock `useDwell`/`useDwellFusion` without
`fusionConfidence` in some fixtures; `ContentViewer`'s default
`fusionConfidence = 0` means no highlight renders when it is absent, which
these tests do not assert against either way.

- [ ] **Step 7: Mutation check**

Temporarily change `fusionConfidence >= HIGHLIGHT_CONFIDENCE_THRESHOLD` to
`true` (always highlight) and confirm the "below the threshold" test fails;
restore.

- [ ] **Step 8: Stage for review**

```bash
git add frontend/src/content/ContentViewer.jsx frontend/src/content/ContentViewer.test.jsx frontend/src/pages/StudySession.jsx
```

---

### Task 6: Frontend — `useAnchoredPosition`

**Files:**
- Create: `frontend/src/intervention/useAnchoredPosition.js`
- Test: `frontend/src/intervention/useAnchoredPosition.test.js`

**Interfaces:**
- Produces: `useAnchoredPosition(element: HTMLElement|null) -> { top, left, width, height } | null`.

- [ ] **Step 1: Write the failing tests**

```javascript
// frontend/src/intervention/useAnchoredPosition.test.js
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAnchoredPosition } from "./useAnchoredPosition";

function elementAt(rect) {
  const el = document.createElement("div");
  Object.defineProperty(el, "getBoundingClientRect", { value: () => rect });
  return el;
}

beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", (cb) => { cb(); return 1; });
  vi.stubGlobal("cancelAnimationFrame", () => {});
});
afterEach(() => vi.unstubAllGlobals());

describe("useAnchoredPosition", () => {
  it("returns null when there is no element", () => {
    const { result } = renderHook(() => useAnchoredPosition(null));
    expect(result.current).toBeNull();
  });

  it("returns the element's rect immediately", () => {
    const el = elementAt({ top: 10, left: 20, width: 300, height: 40 });
    const { result } = renderHook(() => useAnchoredPosition(el));
    expect(result.current).toEqual({ top: 10, left: 20, width: 300, height: 40 });
  });

  it("updates the rect on scroll", () => {
    let rect = { top: 10, left: 20, width: 300, height: 40 };
    const el = document.createElement("div");
    Object.defineProperty(el, "getBoundingClientRect", { value: () => rect });
    const { result } = renderHook(() => useAnchoredPosition(el));

    rect = { top: -50, left: 20, width: 300, height: 40 };
    act(() => window.dispatchEvent(new Event("scroll")));
    expect(result.current.top).toBe(-50);
  });

  it("updates the rect on resize", () => {
    let rect = { top: 10, left: 20, width: 300, height: 40 };
    const el = document.createElement("div");
    Object.defineProperty(el, "getBoundingClientRect", { value: () => rect });
    const { result } = renderHook(() => useAnchoredPosition(el));

    rect = { top: 10, left: 20, width: 150, height: 40 };
    act(() => window.dispatchEvent(new Event("resize")));
    expect(result.current.width).toBe(150);
  });

  it("returns null again when the element becomes null", () => {
    const el = elementAt({ top: 1, left: 1, width: 1, height: 1 });
    const { result, rerender } = renderHook(({ element }) => useAnchoredPosition(element), {
      initialProps: { element: el },
    });
    expect(result.current).not.toBeNull();
    rerender({ element: null });
    expect(result.current).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/intervention/useAnchoredPosition.test.js`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```javascript
// frontend/src/intervention/useAnchoredPosition.js
/**
 * Tracks a DOM element's bounding rect across scroll/resize, so the
 * paragraph popup (ParagraphPopup.jsx) can stay anchored beside whichever
 * paragraph is currently focused, following the page as it scrolls.
 * Returns null when there is no element to track (nothing focused, or the
 * element has not been registered yet).
 */
import { useEffect, useState } from "react";

export function useAnchoredPosition(element) {
  const [rect, setRect] = useState(null);

  useEffect(() => {
    if (!element) {
      setRect(null);
      return undefined;
    }

    let frame = null;

    function measure() {
      const { top, left, width, height } = element.getBoundingClientRect();
      setRect({ top, left, width, height });
    }

    function scheduleMeasure() {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        measure();
      });
    }

    measure();
    window.addEventListener("scroll", scheduleMeasure, { passive: true, capture: true });
    window.addEventListener("resize", scheduleMeasure, { passive: true });

    return () => {
      window.removeEventListener("scroll", scheduleMeasure, { capture: true });
      window.removeEventListener("resize", scheduleMeasure);
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [element]);

  return rect;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/intervention/useAnchoredPosition.test.js`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Mutation check**

Temporarily remove the `measure();` call that runs immediately (before the
event listeners are attached) and confirm "returns the element's rect
immediately" fails (rect stays `null` until the first scroll/resize);
restore.

- [ ] **Step 6: Stage for review**

```bash
git add frontend/src/intervention/useAnchoredPosition.js frontend/src/intervention/useAnchoredPosition.test.js
```

---

### Task 7: Frontend — `useParagraphPopup`

**Files:**
- Create: `frontend/src/intervention/useParagraphPopup.js`
- Test: `frontend/src/intervention/useParagraphPopup.test.js`

**Interfaces:**
- Consumes: the existing `useIntervention()` return shape
  (`{ current, content, loading, accepted, accept, complete, dismiss }`,
  unmodified) and `activeChunkId: string|null`.
- Produces: `useParagraphPopup({ intervention, activeChunkId }) -> { ...intervention, collapsed: boolean, toggleCollapsed: () => void }`.

- [ ] **Step 1: Write the failing tests**

```javascript
// frontend/src/intervention/useParagraphPopup.test.js
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useParagraphPopup } from "./useParagraphPopup";

function fakeIntervention(overrides = {}) {
  return {
    current: null,
    content: null,
    loading: false,
    accepted: false,
    accept: vi.fn(),
    complete: vi.fn(),
    dismiss: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useParagraphPopup", () => {
  it("does not close while the learner stays on the SAME paragraph, however long", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    act(() => vi.advanceTimersByTime(60_000));
    expect(intervention.complete).not.toHaveBeenCalled();
  });

  it("closes once a different chunk has been active continuously for the confirm window", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(2999));
    expect(intervention.complete).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(2));
    expect(intervention.complete).toHaveBeenCalledTimes(1);
  });

  it("cancels the close if the learner returns before the confirm window elapses", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(2000));
    rerender({ activeChunkId: "3" }); // back before the 3s window elapsed
    act(() => vi.advanceTimersByTime(2000));
    expect(intervention.complete).not.toHaveBeenCalled();
  });

  it("restarts the confirm window on a second, later departure rather than crediting the earlier one", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(2000));
    rerender({ activeChunkId: "3" });
    rerender({ activeChunkId: "5" });
    act(() => vi.advanceTimersByTime(2000));
    expect(intervention.complete).not.toHaveBeenCalled(); // only 2s since the second departure
    act(() => vi.advanceTimersByTime(1000));
    expect(intervention.complete).toHaveBeenCalledTimes(1);
  });

  it("treats activeChunkId becoming null the same as a paragraph change", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: null });
    act(() => vi.advanceTimersByTime(3000));
    expect(intervention.complete).toHaveBeenCalledTimes(1);
  });

  it("does nothing when there is no current intervention", () => {
    const intervention = fakeIntervention({ current: null });
    renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    act(() => vi.advanceTimersByTime(10_000));
    expect(intervention.complete).not.toHaveBeenCalled();
  });

  it("exposes a collapsed flag that toggles independently of the close timer", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { result, rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    expect(result.current.collapsed).toBe(false);
    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(true);

    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(3000));
    expect(intervention.complete).toHaveBeenCalledTimes(1); // collapsing never pauses the timer
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/intervention/useParagraphPopup.test.js`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```javascript
// frontend/src/intervention/useParagraphPopup.js
/**
 * Adds paragraph-identity-based auto-close on top of the existing
 * useIntervention(): the popup stays open for as long as the learner is
 * anywhere in the SAME paragraph (activeChunkId === the intervention's own
 * chunk_id) - however long, regardless of which word or line inside it -
 * and closes only once a DIFFERENT chunk (or no chunk) has been the answer
 * continuously for PARAGRAPH_CHANGE_CONFIRM_MS. This is a flicker guard, not
 * a re-trigger on every momentary look-away; returning before the window
 * elapses cancels the close entirely (see the design spec, section 4.2).
 *
 * Depends only on primitive values and useIntervention's own stable
 * `complete` callback - never on the whole `intervention` object, which is
 * a fresh literal every render (the exact class of bug fixed in the prior
 * plan's Critical 1: depending on an unstable object identity tears down
 * and recreates effects on every render).
 */
import { useEffect, useRef, useState } from "react";

export const PARAGRAPH_CHANGE_CONFIRM_MS = 3000;

export function useParagraphPopup({ intervention, activeChunkId }) {
  const [collapsed, setCollapsed] = useState(false);
  const timerRef = useRef(null);

  const currentInterventionId = intervention.current?.intervention_id ?? null;
  const currentChunkId = intervention.current?.chunk_id ?? null;
  const complete = intervention.complete;

  useEffect(() => {
    if (!currentInterventionId) {
      setCollapsed(false);
      return undefined;
    }

    const stillOnSameParagraph = activeChunkId === currentChunkId;

    if (stillOnSameParagraph) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return undefined;
    }

    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      complete();
    }, PARAGRAPH_CHANGE_CONFIRM_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [activeChunkId, currentInterventionId, currentChunkId, complete]);

  return {
    ...intervention,
    collapsed,
    toggleCollapsed: () => setCollapsed((value) => !value),
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/intervention/useParagraphPopup.test.js`
Expected: PASS, all 7 tests.

- [ ] **Step 5: Mutation check**

Temporarily change `const stillOnSameParagraph = activeChunkId === currentChunkId;`
to `const stillOnSameParagraph = true;` (always) and confirm "closes once a
different chunk has been active..." fails (never closes); restore.

- [ ] **Step 6: Stage for review**

```bash
git add frontend/src/intervention/useParagraphPopup.js frontend/src/intervention/useParagraphPopup.test.js
```

---

### Task 8: Frontend — `ParagraphPopup` component

**Files:**
- Modify: `frontend/src/intervention/InterventionHost.jsx` (export `GeneratedText`)
- Create: `frontend/src/intervention/ParagraphPopup.jsx`
- Test: `frontend/src/intervention/ParagraphPopup.test.jsx`

**Interfaces:**
- Consumes: `useAnchoredPosition` (Task 6), exported `GeneratedText` from
  `InterventionHost.jsx`, `QuestionInput` (existing,
  `frontend/src/features/ai-assistant/QuestionInput.jsx`), `Button`
  (existing, `frontend/src/ui`).
- Produces: `ParagraphPopup` component, props:
  `{ chunkElement, intervention, content, collapsed, onToggleCollapsed, onComplete, onDismiss, followUpQuestion, onFollowUpQuestionChange, onAskFollowUp, followUpLoading }`.

- [ ] **Step 1: Export `GeneratedText`**

In `frontend/src/intervention/InterventionHost.jsx`, change:

```javascript
function GeneratedText({ intervention, content, onComplete, onDismiss }) {
```

to:

```javascript
export function GeneratedText({ intervention, content, onComplete, onDismiss }) {
```

(No other change to this file in this task - `InterventionHost`'s own
default export and its internal usage of `GeneratedText` are unaffected by
adding a named export alongside.)

- [ ] **Step 2: Write the failing tests**

```javascript
// frontend/src/intervention/ParagraphPopup.test.jsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ParagraphPopup from "./ParagraphPopup";

function elementAt(rect) {
  const el = document.createElement("div");
  Object.defineProperty(el, "getBoundingClientRect", { value: () => rect });
  return el;
}

const intervention = { intervention_id: "i1", chunk_id: "3", reason: "Signs of difficulty." };
const content = { generated: "A simpler version of the paragraph.", original: "The original passage." };

function baseProps(overrides = {}) {
  return {
    chunkElement: elementAt({ top: 100, left: 0, width: 600, height: 80 }),
    intervention,
    content,
    collapsed: false,
    onToggleCollapsed: vi.fn(),
    onComplete: vi.fn(),
    onDismiss: vi.fn(),
    followUpQuestion: "",
    onFollowUpQuestionChange: vi.fn(),
    onAskFollowUp: vi.fn(),
    followUpLoading: false,
    ...overrides,
  };
}

describe("ParagraphPopup", () => {
  it("falls back to an unpositioned (bottom-of-flow) render when there is no chunk element to anchor to, rather than rendering nothing", () => {
    // Per spec section 6: this should not happen in practice (ContentViewer
    // registers every chunk), but the content must still reach the learner
    // if it ever does, not silently disappear.
    render(<ParagraphPopup {...baseProps({ chunkElement: null })} />);
    expect(screen.getByText(content.generated)).toBeInTheDocument();
  });

  it("renders nothing when there is no generated content yet", () => {
    const { container } = render(<ParagraphPopup {...baseProps({ content: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the generated text and an inline follow-up question box", () => {
    render(<ParagraphPopup {...baseProps()} />);
    expect(screen.getByText(content.generated)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ask about this section/i)).toBeInTheDocument();
  });

  it("collapses to a small reopen control, hiding the generated content", () => {
    render(<ParagraphPopup {...baseProps({ collapsed: true })} />);
    expect(screen.queryByText(content.generated)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show help for this paragraph/i })).toBeInTheDocument();
  });

  it("calls onToggleCollapsed from the collapsed reopen control", () => {
    const onToggleCollapsed = vi.fn();
    render(<ParagraphPopup {...baseProps({ collapsed: true, onToggleCollapsed })} />);
    fireEvent.click(screen.getByRole("button", { name: /show help for this paragraph/i }));
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it("calls onDismiss from its own close control", () => {
    const onDismiss = vi.fn();
    render(<ParagraphPopup {...baseProps({ onDismiss })} />);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("submits a typed follow-up question", () => {
    const onAskFollowUp = vi.fn();
    render(<ParagraphPopup {...baseProps({ followUpQuestion: "Why is this true?", onAskFollowUp })} />);
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onAskFollowUp).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/intervention/ParagraphPopup.test.jsx`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Write the implementation**

```jsx
// frontend/src/intervention/ParagraphPopup.jsx
/**
 * The anchored replacement for InterventionHost's bottom-of-page rendering
 * of simplify_content/bullet_summary: positioned beside the paragraph it is
 * about (useAnchoredPosition), its own scroll for long content, a manual
 * dismiss and a collapse/reopen toggle, and an inline follow-up question box
 * that answers in place rather than sending the learner to the sticky panel.
 *
 * Lifecycle (when it opens/closes) is owned by useParagraphPopup, not here -
 * this component only renders whatever it is currently told to.
 */
import { useEffect, useState } from "react";
import { ChevronUp, X } from "lucide-react";

import { GeneratedText } from "./InterventionHost";
import { useAnchoredPosition } from "./useAnchoredPosition";
import { QuestionInput } from "../features/ai-assistant/QuestionInput";
import { Button } from "../ui";

const WIDE_BREAKPOINT_PX = 1024;
const POPUP_WIDTH_PX = 360;

function useIsWide() {
  const [isWide, setIsWide] = useState(
    typeof window !== "undefined" ? window.innerWidth >= WIDE_BREAKPOINT_PX : true
  );
  useEffect(() => {
    function onResize() {
      setIsWide(window.innerWidth >= WIDE_BREAKPOINT_PX);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return isWide;
}

export default function ParagraphPopup({
  chunkElement,
  intervention,
  content,
  collapsed,
  onToggleCollapsed,
  onComplete,
  onDismiss,
  followUpQuestion,
  onFollowUpQuestionChange,
  onAskFollowUp,
  followUpLoading,
}) {
  const rect = useAnchoredPosition(chunkElement);
  const isWide = useIsWide();

  if (!content?.generated) return null;

  // Should not happen - ContentViewer registers every chunk it renders, so
  // this hook always has an element for the intervention's own chunk_id -
  // but the content must still reach the learner if it ever does. Anchored
  // positioning is a presentation refinement, not a condition for showing
  // the content at all.
  const canAnchor = Boolean(chunkElement) && Boolean(rect);
  const positionStyle = !canAnchor
    ? { position: "static", marginTop: 8 }
    : isWide
    ? { position: "fixed", top: Math.max(8, rect.top), right: 16, width: POPUP_WIDTH_PX, zIndex: 800 }
    : { position: "static", marginTop: 8 };

  if (collapsed) {
    return (
      <div style={isWide ? positionStyle : undefined}>
        <Button variant="secondary" onClick={onToggleCollapsed}>
          <ChevronUp size={14} strokeWidth={1.75} aria-hidden="true" />
          Show help for this paragraph
        </Button>
      </div>
    );
  }

  return (
    <div
      style={{
        ...positionStyle,
        maxHeight: "min(60vh, 420px)",
        overflowY: "auto",
      }}
      className="rounded-card shadow-floating border border-line bg-surface"
    >
      <div className="flex justify-end gap-1 px-2 pt-2">
        <Button variant="quiet" onClick={onToggleCollapsed} aria-label="Collapse">
          Collapse
        </Button>
        <Button variant="quiet" onClick={onDismiss} aria-label="Dismiss">
          <X size={14} strokeWidth={1.75} aria-hidden="true" />
        </Button>
      </div>

      <GeneratedText
        intervention={intervention}
        content={content}
        onComplete={onComplete}
        onDismiss={onDismiss}
      />

      <div className="px-3 pb-3">
        <QuestionInput
          value={followUpQuestion}
          onChange={onFollowUpQuestionChange}
          onSubmit={onAskFollowUp}
          disabled={followUpLoading}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/intervention/ParagraphPopup.test.jsx`
Expected: PASS, all 7 tests.

- [ ] **Step 6: Run `InterventionHost`'s own existing tests to confirm the export change is safe**

Run: `cd frontend && npx vitest run src/intervention/InterventionHost.test.jsx`
(If this file does not exist under this exact name, run
`npx vitest run src/intervention/` and confirm every file in that directory
still passes - `InterventionHost`'s behavior is unchanged, only one function
gained a second, named export.)
Expected: PASS, unchanged.

- [ ] **Step 7: Mutation check**

Temporarily change `if (!content?.generated) return null;` to
`if (true) return null;` and confirm BOTH "falls back to an unpositioned
render..." and "shows the generated text..." fail (nothing ever renders);
restore. Then temporarily change `const canAnchor = Boolean(chunkElement) && Boolean(rect);`
to `const canAnchor = true;` and confirm "falls back to an unpositioned
render when there is no chunk element..." fails (it would try to use
`rect.top` while `rect` is `null`, throwing, rather than falling back);
restore.

- [ ] **Step 8: Stage for review**

```bash
git add frontend/src/intervention/InterventionHost.jsx frontend/src/intervention/ParagraphPopup.jsx frontend/src/intervention/ParagraphPopup.test.jsx
```

---

### Task 9: Frontend — `AssistantPanel` loads persistent history on mount

**Files:**
- Modify: `frontend/src/features/ai-assistant/assistantApi.js`
- Modify: `frontend/src/features/ai-assistant/AssistantPanel.jsx`
- Modify: `frontend/src/features/ai-assistant/AssistantPanel.test.jsx` (existing — extend)

**Interfaces:**
- Produces: `fetchAssistantHistory(options) -> Promise<Array<{id, role, content, source, trigger, content_id, chunk_id, session_id, timestamp}>>`.
- `AssistantPanel` gains an optional prop `historyClient = fetchAssistantHistory`
  (same override-for-testing pattern its existing `apiClient`/`suggestionsClient`
  props already use).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/features/ai-assistant/AssistantPanel.test.jsx` (existing
file — follow its existing render/mock conventions for `apiClient`):

```javascript
  it("loads persistent history on mount and renders it as prior messages", async () => {
    const historyClient = vi.fn().mockResolvedValue([
      { id: "1", role: "user", content: "An earlier question", source: "panel" },
      { id: "2", role: "assistant", content: "An earlier answer", source: "panel" },
    ]);
    render(<AssistantPanel historyClient={historyClient} />);
    expect(await screen.findByText("An earlier question")).toBeInTheDocument();
    expect(screen.getByText("An earlier answer")).toBeInTheDocument();
    expect(historyClient).toHaveBeenCalledTimes(1);
  });

  it("starts with an empty conversation when history loading fails", async () => {
    const historyClient = vi.fn().mockRejectedValue(new Error("network"));
    render(<AssistantPanel historyClient={historyClient} />);
    await waitFor(() => expect(historyClient).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/an earlier/i)).not.toBeInTheDocument();
  });
```

(Add `waitFor` to this file's existing `@testing-library/react` import if
not already imported.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/ai-assistant/AssistantPanel.test.jsx`
Expected: FAIL — 2 new tests fail (no history is ever fetched, "An earlier
question" never renders).

- [ ] **Step 3: Add `fetchAssistantHistory`**

In `frontend/src/features/ai-assistant/assistantApi.js`, add:

```javascript
/**
 * The learner's own persistent assistant conversation, newest first as the
 * server returns it - reversed here so the panel can append to it in
 * chronological order the same way it already appends new messages.
 */
export async function fetchAssistantHistory(options = {}) {
  const response = await api.get("/assistant/history", { signal: options.signal });
  if (!Array.isArray(response?.data?.messages)) {
    throw new Error("Assistant service returned an invalid history.");
  }
  return [...response.data.messages].reverse();
}
```

- [ ] **Step 4: Load it in `AssistantPanel.jsx`**

Add the import:

```javascript
import { fetchAssistantHistory, fetchSuggestedQuestions, sendAssistantMessage } from "./assistantApi";
```

Add `historyClient = fetchAssistantHistory` to the destructured props, and a
mount-only effect (placed near the top of the component body, before the
existing session-reset effect):

```javascript
  useEffect(() => {
    let cancelled = false;
    historyClient()
      .then((history) => {
        if (cancelled || !Array.isArray(history) || history.length === 0) return;
        setMessages(
          history.map((entry) => ({
            id: nextMessageId.current++,
            role: entry.role,
            content: entry.content,
          }))
        );
      })
      .catch(() => {
        // A history that fails to load leaves the conversation empty -
        // today's actual starting state - rather than blocking the panel.
      });
    return () => {
      cancelled = true;
    };
    // Runs once, on mount, regardless of studyContext - a remount (closing
    // and reopening the panel) is exactly when this should re-fetch, since
    // AssistantPanel already loses its in-memory `messages` state on every
    // remount today.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/ai-assistant/AssistantPanel.test.jsx`
Expected: PASS, all tests (existing + 2 new).

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS — `AssistantPanel.integration.test.jsx` and
`AssistantPanel.suggestions.test.jsx` do not pass `historyClient`, so they
get the real default (`fetchAssistantHistory`), which will attempt a real
`api.get` call; confirm this does not break those tests (they likely already
mock the underlying `api` client module, or the call rejects harmlessly per
Step 4's catch-and-ignore). If any pre-existing test does start failing
because of an unmocked network call, add a `vi.mock` for
`./assistantApi`'s `fetchAssistantHistory` in that file, resolving to `[]`,
matching this file's existing mocking conventions - do not change
`AssistantPanel.jsx` itself to work around a test gap.

- [ ] **Step 7: Mutation check**

Temporarily change `if (cancelled || !Array.isArray(history) || history.length === 0) return;`
to always `return;` and confirm "loads persistent history on mount" fails
(no messages render); restore.

- [ ] **Step 8: Stage for review**

```bash
git add frontend/src/features/ai-assistant/assistantApi.js frontend/src/features/ai-assistant/AssistantPanel.jsx frontend/src/features/ai-assistant/AssistantPanel.test.jsx
```

---

### Task 10: Frontend — wire `ParagraphPopup` into `StudySession.jsx`

**Files:**
- Modify: `frontend/src/pages/StudySession.jsx`
- Modify: `frontend/src/pages/StudySession.chunkWiring.test.jsx` (existing — extend)

**Interfaces:**
- Consumes: `useParagraphPopup` (Task 7), `ParagraphPopup` (Task 8),
  `sendAssistantMessage` (existing, for the popup's inline follow-up).
- Produces: the bottom-of-page `InterventionHost` render (previously at
  `StudySession.jsx:407-417`) is replaced by an anchored `ParagraphPopup`.

This task needs one small piece of new bookkeeping: `ParagraphPopup` needs
the actual DOM element for the intervention's own `chunk_id` to anchor to.
`useDwellFusion`'s internal element map is not exposed - rather than
changing that hook (out of scope, per Global Constraints), `StudySession`
keeps its own small parallel map, populated through the same `onChunkRef`
callback `ContentViewer` already calls for every chunk.

- [ ] **Step 1: Write the failing test**

This file (`StudySession.chunkWiring.test.jsx`) already has, at lines 62-72:

```javascript
vi.mock("../intervention/useIntervention", () => ({
  useIntervention: () => ({
    current: null,
    content: null,
    loading: false,
    accepted: false,
    accept: vi.fn(),
    complete: vi.fn(),
    dismiss: vi.fn(),
  }),
}));
```

a fixed factory with no way to change what it returns per-test. Change it to
a `vi.fn()` with that same object as its default, so this one new test can
override it:

```javascript
const useInterventionMock = vi.fn(() => ({
  current: null,
  content: null,
  loading: false,
  accepted: false,
  accept: vi.fn(),
  complete: vi.fn(),
  dismiss: vi.fn(),
}));
vi.mock("../intervention/useIntervention", () => ({
  useIntervention: () => useInterventionMock(),
}));
```

Add `import { beforeEach } from "vitest";` is already covered by this file's
existing `import { beforeEach, describe, expect, it, vi } from "vitest";`
line - no new import needed there. Add, near this file's existing
`beforeEach(() => { captureArgs.length = 0; assistantProps.length = 0; });`:

```javascript
  useInterventionMock.mockClear();
```

Then add the new test:

```javascript
  it("anchors the popup to the chunk the intervention is actually about, not wherever the page happens to render it", () => {
    // mockContent (this file's existing fixture, lines 74-86) has chunks
    // "0" and "1"; the useDwell mock (lines 50-61) fixes activeChunkId to
    // "1" - this intervention is deliberately for chunk "1" too, so the
    // popup's anchoring can be checked against the real registered element.
    useInterventionMock.mockReturnValue({
      current: { intervention_id: "int-1", chunk_id: "1" },
      content: { generated: "Simplified.", original: "Second paragraph text." },
      loading: false,
      accepted: false,
      accept: vi.fn(),
      complete: vi.fn(),
      dismiss: vi.fn(),
    });
    render(
      <MemoryRouter>
        <StudySession contentId="content-1" />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));
    expect(screen.getByText("Simplified.")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/StudySession.chunkWiring.test.jsx`
Expected: FAIL — "Simplified." is not on screen yet (still rendered via the
old bottom-of-page `InterventionHost`, unanchored, or not rendered at all
depending on current mocks).

- [ ] **Step 3: Add the chunk-element bookkeeping and wire `ParagraphPopup`**

In `frontend/src/pages/StudySession.jsx`, add near the top of the component
body (alongside the existing `captureRef`):

```javascript
  const chunkElementsRef = useRef(new Map()); // chunk_id -> DOM element
  const registerChunkElement = useCallback((chunkId, element) => {
    dwell.register(chunkId, element);
    if (element) {
      chunkElementsRef.current.set(chunkId, element);
    } else {
      chunkElementsRef.current.delete(chunkId);
    }
  }, [dwell]);
```

Change the `<ContentViewer onChunkRef={dwell.register} .../>` from Task 5 to
use `registerChunkElement` instead of `dwell.register` directly:

```jsx
              <ContentViewer
                content={document_.content}
                onChunkRef={registerChunkElement}
                activeChunkId={dwell.activeChunkId}
                fusionConfidence={dwell.fusionConfidence}
              />
```

Add state for the popup's inline follow-up composer, near the existing
`assistantOpen` state:

```javascript
  const [popupFollowUp, setPopupFollowUp] = useState("");
  const [popupFollowUpLoading, setPopupFollowUpLoading] = useState(false);

  const popup = useParagraphPopup({ intervention, activeChunkId: dwell.activeChunkId });

  const askPopupFollowUp = async () => {
    const question = popupFollowUp.trim();
    if (!question || !popup.current) return;
    setPopupFollowUpLoading(true);
    try {
      await sendAssistantMessage({
        question,
        session_id: capture.sessionId,
        content_id: contentId,
        current_chunk: {
          chunk_id: popup.current.chunk_id,
          text: document_.content?.chunks?.find((c) => c.chunk_id === popup.current.chunk_id)?.text || "",
        },
        source: "popup",
      });
      setPopupFollowUp("");
    } catch {
      // Best effort - the popup's own generated content is unaffected either way.
    } finally {
      setPopupFollowUpLoading(false);
    }
  };
```

Add the imports:

```javascript
import { useCallback, useMemo, useRef, useState } from "react";
```

(add `useCallback` to the existing React import line if not already there)

```javascript
import ParagraphPopup from "../intervention/ParagraphPopup";
import { useParagraphPopup } from "../intervention/useParagraphPopup";
import { sendAssistantMessage } from "../features/ai-assistant/assistantApi";
```

Replace the existing bottom-of-page block (the one identified at
`StudySession.jsx:404-417`, `InterventionHost` inside
`<div className="w-full max-w-[620px]">`) with:

```jsx
        <ParagraphPopup
          chunkElement={popup.current ? chunkElementsRef.current.get(popup.current.chunk_id) : null}
          intervention={popup.current}
          content={popup.content}
          collapsed={popup.collapsed}
          onToggleCollapsed={popup.toggleCollapsed}
          onComplete={popup.complete}
          onDismiss={popup.dismiss}
          followUpQuestion={popupFollowUp}
          onFollowUpQuestionChange={setPopupFollowUp}
          onAskFollowUp={askPopupFollowUp}
          followUpLoading={popupFollowUpLoading}
        />
```

(The `loading`/`accepted`/break-suggestion/assistant-help-prompt cases
`InterventionHost` also handled are intentionally NOT covered by
`ParagraphPopup` - those are not paragraph-anchored per the spec, which
scopes this redesign to `simplify_content`/`bullet_summary` only. Keep a
second, small render site for `break_suggestion`/`assistant_help_prompt`
using the existing `InterventionHost` bottom-of-page card unchanged, gated
on `intervention.current && !needsGeneratedText(intervention.current.intervention_type)`,
importing `needsGeneratedText` from `../intervention/constants`.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/StudySession.chunkWiring.test.jsx`
Expected: PASS, all tests (existing + 1 new).

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS — every other `StudySession.*.test.jsx` file must still pass;
if any fails because it asserted on the old bottom-of-page
`InterventionHost` rendering for `simplify_content`/`bullet_summary`
specifically, update that assertion to look for the new `ParagraphPopup`
rendering instead (its content is the same `GeneratedText` markup, reused,
so most such assertions - text content, button labels - should already
match unchanged).

- [ ] **Step 6: Mutation check**

Temporarily change
`chunkElementsRef.current.get(popup.current.chunk_id)` to always return
`null` and confirm the new anchoring test fails ("Simplified." never
renders, since `ParagraphPopup` returns null without a `chunkElement`);
restore.

- [ ] **Step 7: Stage for review**

```bash
git add frontend/src/pages/StudySession.jsx frontend/src/pages/StudySession.chunkWiring.test.jsx
```

---

## Final full-suite check

- [ ] **Backend:** `cd backend && .venv/Scripts/python.exe -m pytest -q` — expect all prior tests plus this plan's new tests passing, 0 failures.
- [ ] **Frontend:** `cd frontend && npx vitest run` — expect all prior tests plus this plan's new tests passing, 0 failures.
- [ ] **Frontend build:** `cd frontend && npm run build` — expect a clean build.

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

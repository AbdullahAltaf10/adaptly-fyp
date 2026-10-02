import os
import sys
import time

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
    time.sleep(0.001)  # Windows' time.time() resolution can tie two fast calls otherwise
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


from unittest.mock import patch  # noqa: E402

from app.ai_assistant import service  # noqa: E402


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

"""The assistant knowing how the session is going (scope 6.6).

Three properties, each easy to break without anything visibly failing:

  * the state comes from the SERVER's record, never from the request, so a
    client cannot forge it and one learner's state cannot reach another
  * it changes how the assistant writes and never tells the learner they are
    being measured (scope 6.4 and 6.8)
  * a stale or missing state changes nothing, which is the safe way to fail
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.ai_assistant import prompts, service
from app.ai_assistant.context import build_assistant_context
from app.ai_assistant.schemas import AssistantMessageRequest
from app.auth.dependencies import get_current_user
from app.engagement import latest_state
from app.main import app

client = TestClient(app)


def _request(session_id="s1", **extra):
    return AssistantMessageRequest.model_validate(
        {
            "question": "What does amortisation mean?",
            "session_id": session_id,
            "content_id": "c1",
            "current_chunk": {"chunk_id": "ch1", "text": "Amortisation spreads a cost."},
            **extra,
        }
    )


def _prompt(state):
    request = _request()
    context = build_assistant_context(request, engagement_state=state)
    return prompts.build_assistant_prompt(context)


@pytest.fixture(autouse=True)
def clean_state():
    latest_state._latest.clear()
    yield
    latest_state._latest.clear()
    app.dependency_overrides.clear()


# ----------------------------------------------------------------- the store

def test_a_recorded_state_is_returned_to_the_same_learner_and_session():
    latest_state.record("u1", "s1", "struggling", now=100.0)
    assert latest_state.get("u1", "s1", now=110.0) == "struggling"


def test_one_learners_state_never_reaches_another():
    latest_state.record("u1", "s1", "struggling", now=100.0)
    assert latest_state.get("u2", "s1", now=101.0) is None
    assert latest_state.get("u1", "another-session", now=101.0) is None


def test_a_stale_state_is_treated_as_unknown():
    # Analyze runs about every ten seconds. A minute-old state describes a
    # moment the learner has already moved on from.
    latest_state.record("u1", "s1", "struggling", now=100.0)
    assert latest_state.get("u1", "s1", now=100.0 + latest_state.MAX_AGE_SECONDS) == "struggling"
    assert latest_state.get("u1", "s1", now=100.0 + latest_state.MAX_AGE_SECONDS + 1) is None


def test_it_is_forgotten_when_the_session_ends():
    latest_state.record("u1", "s1", "drifting", now=100.0)
    latest_state.clear("u1", "s1")
    assert latest_state.get("u1", "s1", now=101.0) is None


def test_recording_never_raises():
    # It sits on the analyze endpoint's hot path; a fault here must not take
    # engagement detection down.
    latest_state._latest = None  # something that would raise on item assignment
    try:
        latest_state.record("u1", "s1", "focused")
    finally:
        latest_state._latest = {}


# ------------------------------------------------------------- the prompt

@pytest.mark.parametrize("state", ["drifting", "struggling", "fatigued"])
def test_a_difficult_state_adds_style_guidance(state):
    prompt = _prompt(state)
    assert "<engagement_style_guidance>" in prompt
    assert "Adaptly-generated" in prompt


@pytest.mark.parametrize("state", ["focused", "recovered", None, "deep_thinking", "nonsense"])
def test_a_fine_or_unknown_state_adds_nothing_at_all(state):
    # Not an empty section - no section. An empty one invites the model to
    # comment on it.
    assert "<engagement_style_guidance>" not in _prompt(state)


@pytest.mark.parametrize("state", ["drifting", "struggling", "fatigued"])
def test_the_assistant_is_told_not_to_volunteer_the_state(state):
    # Scope 6.4 asks for support without any alert and 6.8 for no indicators of
    # measurement. "I can see you are struggling" is exactly that, and reads as
    # surveillance.
    prompt = _prompt(state)
    assert "Do not bring up, hint at or comment on" in prompt
    assert "Do not say what they currently indicate" in prompt


@pytest.mark.parametrize("state", ["drifting", "struggling", "fatigued"])
def test_the_assistant_is_never_told_to_deny_being_measured(state):
    # The first version forbade mentioning the camera at all. A live Gemini
    # call then answered a direct question with "I don't have any way to see or
    # track how you're feeling" - a lie, since the camera is measuring
    # engagement and the pre-session screen says so. The rule is about what to
    # VOLUNTEER; asked directly, the answer must be true.
    prompt = _prompt(state)
    assert "answer honestly" in prompt
    assert "Never claim it does not" in prompt
    # Seen live: "I cannot see those measurements". The assistant does receive a
    # coarse state, so that too is a denial and is ruled out explicitly.
    assert "never claim you cannot see or have no access" in prompt
    assert "never mention a camera" not in prompt
    assert "no video is recorded or stored" in prompt


def test_the_guidance_is_soft_because_the_evidence_is_weak():
    # Struggling recall is about 10% on held-out data, so an assistant that
    # asserted the state would be confidently wrong most of the time.
    prompt = _prompt("struggling")
    assert "may be finding this section hard" in prompt
    assert "is struggling" not in prompt.lower().split("<engagement_style_guidance>")[1].split("</engagement_style_guidance>")[0]


def test_the_state_is_not_placed_in_the_untrusted_section():
    # It is trusted, server-derived guidance. Putting it inside the untrusted
    # JSON blocks would let the model treat it as learner-supplied.
    prompt = _prompt("struggling")
    section = prompt.split("<engagement_style_guidance>")[1].split("</engagement_style_guidance>")[0]
    assert "untrusted" not in section
    untrusted = prompt.split("<session_context_untrusted_json>")[1].split(
        "</session_context_untrusted_json>"
    )[0]
    assert "struggling" not in untrusted


# ------------------------------------------- end to end through the endpoint

def _capture_state(monkeypatch):
    seen = {}

    def fake(request, settings=None, client_factory=None, engagement_state=None, **kwargs):
        # **kwargs so this stub survives the endpoint gaining another
        # server-derived argument - the document glossary was the next one -
        # rather than every engagement test failing for an unrelated reason.
        seen["state"] = engagement_state
        return service.create_mock_response(request), None

    monkeypatch.setattr(service, "create_assistant_response", fake)
    body = {
        "question": "What does amortisation mean?",
        "session_id": "s1",
        "content_id": "c1",
        "current_chunk": {"chunk_id": "ch1", "text": "Amortisation spreads a cost."},
    }
    return seen, body


def _as(uid):
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid, "email": f"{uid}@t.com"}


def test_the_endpoint_passes_the_servers_own_record(monkeypatch):
    _as("u1")
    latest_state.record("u1", "s1", "struggling")
    seen, body = _capture_state(monkeypatch)
    assert client.post("/assistant/messages", json=body).status_code == 200
    assert seen["state"] == "struggling"


@pytest.mark.parametrize(
    "where",
    ["top level", "inside session_context"],
)
def test_a_client_cannot_forge_a_state(monkeypatch, where):
    # The schema forbids unknown fields, so a forged state is refused outright
    # (422) rather than silently ignored - and the service is never reached, so
    # there is no path on which the claimed state could influence the prompt.
    _as("u1")
    seen, body = _capture_state(monkeypatch)
    if where == "top level":
        body["engagement_state"] = "struggling"
    else:
        body["session_context"] = {"status": "active", "engagement_state": "struggling"}

    response = client.post("/assistant/messages", json=body)

    assert response.status_code == 422
    assert "extra_forbidden" in response.text
    assert "state" not in seen


def test_another_learners_state_does_not_leak_into_this_conversation(monkeypatch):
    latest_state.record("someone-else", "s1", "struggling")
    _as("u1")
    seen, body = _capture_state(monkeypatch)
    client.post("/assistant/messages", json=body)
    assert seen["state"] is None


def test_no_state_means_the_normal_style(monkeypatch):
    _as("u1")
    seen, body = _capture_state(monkeypatch)
    client.post("/assistant/messages", json=body)
    assert seen["state"] is None

"""Tests for request-scoped assistant context and conversation preparation."""

from app.ai_assistant.context import MAX_CONTEXT_HISTORY_MESSAGES, build_assistant_context
from app.ai_assistant.prompts import build_assistant_prompt
from app.ai_assistant.schemas import AssistantMessageRequest


def make_request(**overrides: object) -> AssistantMessageRequest:
    payload: dict[str, object] = {
        "question": "What does this mean?",
        "session_id": "session-001",
        "content_id": "content-001",
        "current_chunk": {
            "chunk_id": "chunk-003",
            "text": "Gradient descent updates parameters to reduce error.",
            "section_title": "Gradient Descent",
        },
        "previous_messages": [],
    }
    payload.update(overrides)
    return AssistantMessageRequest.model_validate(payload)


def test_context_builder_keeps_active_chunk_and_required_identifiers() -> None:
    context = build_assistant_context(make_request())

    assert context.chunk.chunk_id == "chunk-003"
    assert context.chunk.text == "Gradient descent updates parameters to reduce error."
    assert context.content.content_id == "content-001"
    assert context.session.session_id == "session-001"


def test_context_builder_includes_optional_metadata_and_preferences() -> None:
    context = build_assistant_context(
        make_request(
            content_context={
                "title": "Introduction to Machine Learning",
                "content_type": "pdf",
                "language": "en",
            },
            session_context={"status": "active", "current_chunk_id": "chunk-003"},
            learner_preferences={"preferred_explanation_mode": "simple"},
        )
    )

    assert context.content.title == "Introduction to Machine Learning"
    assert context.content.content_type == "pdf"
    assert context.session.status == "active"
    assert context.session.current_chunk_id == "chunk-003"
    assert context.learner_preferences is not None
    assert context.learner_preferences.preferred_explanation_mode == "simple"


def test_missing_optional_context_and_empty_conversation_are_safe() -> None:
    context = build_assistant_context(make_request())
    prompt = build_assistant_prompt(context)

    assert context.content.title is None
    assert context.session.status is None
    assert context.learner_preferences is None
    assert context.conversation == []
    assert "What does this mean?" in prompt


def test_history_is_bounded_chronological_and_preserves_first_question() -> None:
    messages = [
        {"role": "user", "message": "What is gradient descent?"},
        {"role": "assistant", "message": "It reduces error step by step."},
    ]
    messages.extend(
        {"role": "user" if index % 2 == 0 else "assistant", "message": f"message-{index}"}
        for index in range(12)
    )
    request = make_request(previous_messages=messages)
    original_messages = [message.model_copy(deep=True) for message in request.previous_messages]

    context = build_assistant_context(request)

    assert len(context.conversation) == MAX_CONTEXT_HISTORY_MESSAGES
    assert context.conversation[0].message == "What is gradient descent?"
    assert [message.message for message in context.conversation[1:]] == [
        "message-5",
        "message-6",
        "message-7",
        "message-8",
        "message-9",
        "message-10",
        "message-11",
    ]
    assert request.previous_messages == original_messages


def test_history_deduplicates_messages_without_cross_session_memory() -> None:
    repeated = {"role": "user", "message": "Please explain the term."}
    first_context = build_assistant_context(
        make_request(session_id="session-001", previous_messages=[repeated, repeated])
    )
    second_context = build_assistant_context(
        make_request(session_id="session-002", previous_messages=[])
    )

    assert len(first_context.conversation) == 1
    assert second_context.session.session_id == "session-002"
    assert second_context.conversation == []


def test_follow_up_prompt_contains_recent_conversation_and_context_categories() -> None:
    context = build_assistant_context(
        make_request(
            content_context={"title": "Introduction to Machine Learning"},
            session_context={"status": "active"},
            learner_preferences={"preferred_explanation_mode": "simple"},
            previous_messages=[
                {"role": "user", "message": "What is gradient descent?"},
                {
                    "role": "assistant",
                    "message": "It gradually adjusts parameters to reduce error.",
                },
            ],
        )
    )
    prompt = build_assistant_prompt(context)

    assert "What does this mean?" in prompt
    assert "What is gradient descent?" in prompt
    assert "Gradient descent updates parameters to reduce error." in prompt
    assert "Introduction to Machine Learning" in prompt
    assert "<document_metadata_untrusted_json>" in prompt
    assert "<active_learning_chunk_untrusted_json>" in prompt
    assert "<session_context_untrusted_json>" in prompt
    assert "<learner_preferences_untrusted_json>" in prompt
    assert "Use shorter sentences and explain unfamiliar terms plainly." in prompt

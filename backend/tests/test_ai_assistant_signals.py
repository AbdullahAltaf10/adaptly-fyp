"""Tests for deterministic, request-scoped conversational support signals."""

import pytest

from app.ai_assistant.context import build_assistant_context
from app.ai_assistant.prompts import build_assistant_prompt
from app.ai_assistant.schemas import AssistantMessageRequest
from app.ai_assistant.signals import classify_conversational_signal


@pytest.mark.parametrize(
    ("message", "expected_signal"),
    [
        ("Explain gradient descent.", "neutral"),
        ("I don't understand this.", "confusion"),
        ("What does this mean?", "confusion"),
        ("Can you explain that again?", "confusion"),
        ("This is really frustrating.", "frustration"),
        ("I've tried this three times and it still makes no sense.", "frustration"),
        ("I still don't understand this and it's frustrating.", "frustration"),
        ("I DON'T UNDERSTAND THIS!", "confusion"),
        ("This example is not bad.", "neutral"),
    ],
)
def test_classifies_current_learner_message(message: str, expected_signal: str) -> None:
    assert classify_conversational_signal(message) == expected_signal


def test_signal_is_trusted_prompt_guidance_not_untrusted_context() -> None:
    request = AssistantMessageRequest.model_validate(
        {
            "question": "I still don't understand this and it is frustrating.",
            "session_id": "session-001",
            "content_id": "content-001",
            "current_chunk": {"chunk_id": "chunk-001", "text": "A learning chunk."},
        }
    )
    prompt = build_assistant_prompt(
        build_assistant_context(request, emotion_signal=classify_conversational_signal(request.question))
    )

    assert "<conversational_support_guidance>" in prompt
    assert "This is Adaptly-generated, request-scoped support guidance." in prompt
    assert "Briefly acknowledge that the material can be difficult" in prompt

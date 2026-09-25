"""Deterministic, context-grounded follow-up questions for the assistant API."""

from app.ai_assistant.schemas import AssistantMessageRequest


def generate_suggested_questions(request: AssistantMessageRequest) -> list[str]:
    """Return three concise follow-up questions for the active learning section.

    Suggestions are generated locally from the current chunk so both mock and
    Gemini modes return the same stable response contract without another
    provider request.
    """
    topic = request.current_chunk.section_title or "this section"
    return [
        f"Can you explain {topic} more simply?",
        f"Can you give me an example of {topic}?",
        f"Why is {topic} important?",
    ]

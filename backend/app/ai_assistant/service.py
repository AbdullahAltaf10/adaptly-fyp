"""Deterministic, local-only assistant behavior for Issue #17."""

from app.ai_assistant.schemas import AssistantMessageRequest, AssistantMessageResponse


def create_mock_response(request: AssistantMessageRequest) -> AssistantMessageResponse:
    """Return a predictable response that confirms minimal learning context use.

    The service intentionally neither persists input nor calls an external provider.
    It references only safe metadata, rather than echoing the learner's question or
    the active chunk's potentially private text.
    """
    section = request.current_chunk.section_title
    section_suffix = f" in the '{section}' section" if section else ""
    answer = (
        f"Mock assistant response for chunk '{request.current_chunk.chunk_id}'"
        f"{section_suffix}. Your question was received with the current learning context."
    )

    return AssistantMessageResponse(
        answer=answer,
        used_context=True,
        response_mode="text",
        session_id=request.session_id,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
    )

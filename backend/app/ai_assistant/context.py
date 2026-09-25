"""Request-scoped assistant context and bounded conversation preparation."""

from collections.abc import Sequence

from app.ai_assistant.schemas import (
    AssistantContext,
    AssistantMessageRequest,
    ConversationMessage,
    EmotionSignal,
    NormalizedContentContext,
    NormalizedSessionContext,
)


MAX_CONTEXT_HISTORY_MESSAGES = 8


def select_conversation_history(
    messages: Sequence[ConversationMessage],
    max_messages: int = MAX_CONTEXT_HISTORY_MESSAGES,
) -> list[ConversationMessage]:
    """Return a deduplicated chronological window without mutating caller data.

    Recent messages are prioritized. If the first learner question would be
    excluded, it replaces the oldest retained recent message so a follow-up still
    has its original topic. The returned list never exceeds ``max_messages``.
    """
    if max_messages < 1:
        return []

    unique_messages: list[ConversationMessage] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        key = (message.role, message.message)
        if key not in seen:
            seen.add(key)
            unique_messages.append(message.model_copy(deep=True))

    if len(unique_messages) <= max_messages:
        return unique_messages

    recent_messages = unique_messages[-max_messages:]
    first_user_message = next(
        (message for message in unique_messages if message.role == "user"),
        None,
    )
    if first_user_message and first_user_message not in recent_messages:
        return [first_user_message, *recent_messages[1:]]
    return recent_messages


def build_assistant_context(
    request: AssistantMessageRequest,
    emotion_signal: EmotionSignal = "neutral",
) -> AssistantContext:
    """Normalize available request data into one prompt-ready context object."""
    content_metadata = request.content_context
    session_metadata = request.session_context

    return AssistantContext(
        question=request.question,
        content=NormalizedContentContext(
            content_id=request.content_id,
            title=content_metadata.title if content_metadata else None,
            content_type=content_metadata.content_type if content_metadata else None,
            language=content_metadata.language if content_metadata else None,
        ),
        chunk=request.current_chunk.model_copy(deep=True),
        session=NormalizedSessionContext(
            session_id=request.session_id,
            status=session_metadata.status if session_metadata else None,
            current_chunk_id=(
                session_metadata.current_chunk_id if session_metadata else None
            ),
        ),
        learner_preferences=(
            request.learner_preferences.model_copy(deep=True)
            if request.learner_preferences
            else None
        ),
        conversation=select_conversation_history(request.previous_messages),
        emotion_signal=emotion_signal,
    )

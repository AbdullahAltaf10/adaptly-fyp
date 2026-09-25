"""Request and response models for the Module 5 assistant API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_ID_LENGTH = 128
MAX_QUESTION_LENGTH = 2_000
MAX_CHUNK_TEXT_LENGTH = 12_000
MAX_SECTION_TITLE_LENGTH = 300
MAX_PREVIOUS_MESSAGES = 20
MAX_MESSAGE_LENGTH = 4_000
MAX_SUGGESTED_QUESTION_LENGTH = 300
SUGGESTED_QUESTION_COUNT = 3
EmotionSignal = Literal["neutral", "confusion", "frustration"]


class AssistantModel(BaseModel):
    """Shared strict model settings for the assistant API."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CurrentChunk(AssistantModel):
    """The content chunk active when the learner asks a question."""

    chunk_id: Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]
    text: Annotated[str, Field(min_length=1, max_length=MAX_CHUNK_TEXT_LENGTH)]
    section_title: Annotated[
        str | None, Field(default=None, max_length=MAX_SECTION_TITLE_LENGTH)
    ]

    @field_validator("chunk_id", "text", "section_title", mode="before")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        """Trim strings and reject values that become blank."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class ConversationMessage(AssistantModel):
    """A prior learner or assistant message supplied for request context."""

    role: Literal["user", "assistant"]
    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)]

    @field_validator("message", mode="before")
    @classmethod
    def reject_blank_message(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class ContentMetadata(AssistantModel):
    """Optional document metadata used to ground an assistant response."""

    title: Annotated[str | None, Field(default=None, max_length=300)]
    content_type: Annotated[str | None, Field(default=None, max_length=64)]
    language: Annotated[str | None, Field(default=None, max_length=20)]

    @field_validator("title", "content_type", "language", mode="before")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class SessionMetadata(AssistantModel):
    """Optional current-session metadata relevant to assistant context."""

    status: Annotated[str | None, Field(default=None, max_length=50)]
    current_chunk_id: Annotated[str | None, Field(default=None, max_length=MAX_ID_LENGTH)]

    @field_validator("status", "current_chunk_id", mode="before")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class LearnerPreferences(AssistantModel):
    """Optional non-sensitive preferences that can adjust explanation style."""

    preferred_explanation_mode: Literal["standard", "simple", "detailed"] | None = None
    preferred_content_mode: Literal["text", "audio", "mixed"] | None = None


class AssistantMessageRequest(AssistantModel):
    """Validated input for one context-aware assistant message."""

    question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_LENGTH)]
    session_id: Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]
    content_id: Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]
    current_chunk: CurrentChunk
    content_context: ContentMetadata | None = None
    session_context: SessionMetadata | None = None
    learner_preferences: LearnerPreferences | None = None
    previous_messages: Annotated[
        list[ConversationMessage], Field(default_factory=list, max_length=MAX_PREVIOUS_MESSAGES)
    ]

    @field_validator("question", "session_id", "content_id", mode="before")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class NormalizedContentContext(AssistantModel):
    """Content metadata with the request's required content identifier."""

    content_id: str
    title: str | None = None
    content_type: str | None = None
    language: str | None = None


class NormalizedSessionContext(AssistantModel):
    """Session metadata with the request's required session identifier."""

    session_id: str
    status: str | None = None
    current_chunk_id: str | None = None


class AssistantContext(AssistantModel):
    """Normalized request-scoped context supplied to the prompt builder."""

    question: str
    content: NormalizedContentContext
    chunk: CurrentChunk
    session: NormalizedSessionContext
    learner_preferences: LearnerPreferences | None = None
    conversation: list[ConversationMessage]
    emotion_signal: EmotionSignal = "neutral"


class AssistantMessageResponse(AssistantModel):
    """Stable Issue #17 response returned by the deterministic mock service."""

    answer: str
    suggested_questions: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_SUGGESTED_QUESTION_LENGTH)]],
        Field(min_length=SUGGESTED_QUESTION_COUNT, max_length=SUGGESTED_QUESTION_COUNT),
    ]
    emotion_signal: EmotionSignal
    used_context: bool
    response_mode: Literal["text"]
    session_id: str
    content_id: str
    chunk_id: str

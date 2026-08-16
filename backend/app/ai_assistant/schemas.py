"""Request and response models for the Module 5 assistant API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_ID_LENGTH = 128
MAX_QUESTION_LENGTH = 2_000
MAX_CHUNK_TEXT_LENGTH = 12_000
MAX_SECTION_TITLE_LENGTH = 300
MAX_PREVIOUS_MESSAGES = 20
MAX_MESSAGE_LENGTH = 4_000


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


class AssistantMessageRequest(AssistantModel):
    """Validated input for one context-aware assistant message."""

    question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_LENGTH)]
    session_id: Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]
    content_id: Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]
    current_chunk: CurrentChunk
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


class AssistantMessageResponse(AssistantModel):
    """Stable Issue #17 response returned by the deterministic mock service."""

    answer: str
    used_context: bool
    response_mode: Literal["text"]
    session_id: str
    content_id: str
    chunk_id: str

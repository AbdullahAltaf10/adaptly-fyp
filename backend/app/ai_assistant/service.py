"""Mock and Gemini-backed behavior for the Module 5 assistant."""

from collections.abc import Callable
import logging
import re
from typing import Any

from app.ai_assistant.context import build_assistant_context
from app.ai_assistant.prompts import build_assistant_prompt
from app.ai_assistant.schemas import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    EmotionSignal,
)
from app.ai_assistant.signals import classify_conversational_signal
from app.ai_assistant.suggestions import generate_suggested_questions
from app.core.config import AssistantSettings, ConfigurationError


logger = logging.getLogger(__name__)
MAX_DIAGNOSTIC_MESSAGE_LENGTH = 500
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(api[_ -]?key|x-goog-api-key|authorization)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"(?i)([?&](?:key|api[_-]?key)=)[^&\s]+"),
)


class AssistantServiceError(RuntimeError):
    """Base exception for safe, provider-independent assistant errors."""


class AssistantConfigurationError(AssistantServiceError):
    """Raised when real assistant mode cannot be configured safely."""


class AssistantProviderError(AssistantServiceError):
    """Raised when Gemini cannot return a usable answer."""


class AssistantProviderTimeoutError(AssistantProviderError):
    """Raised when Gemini does not answer within the configured timeout."""


GeminiClientFactory = Callable[[str, int], Any]


def create_gemini_client(api_key: str, timeout_ms: int) -> Any:
    """Create the official Google Gen AI SDK client only for real Gemini mode."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise AssistantConfigurationError(
            "The Gemini provider is unavailable on this server."
        ) from error

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )


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
        suggested_questions=generate_suggested_questions(request),
        emotion_signal=classify_conversational_signal(request.question),
        used_context=True,
        response_mode="text",
        session_id=request.session_id,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
    )


def _create_response(
    request: AssistantMessageRequest,
    answer: str,
    emotion_signal: EmotionSignal,
) -> AssistantMessageResponse:
    """Preserve the stable Issue #17 response envelope for both modes."""
    return AssistantMessageResponse(
        answer=answer,
        suggested_questions=generate_suggested_questions(request),
        emotion_signal=emotion_signal,
        used_context=True,
        response_mode="text",
        session_id=request.session_id,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
    )


def _extract_response_text(provider_response: Any) -> str:
    """Safely read non-empty text from a Google Gen AI SDK response."""
    try:
        text = provider_response.text
    except Exception as error:
        raise AssistantProviderError("The assistant provider returned no usable answer.") from error

    if not isinstance(text, str) or not text.strip():
        raise AssistantProviderError("The assistant provider returned no usable answer.")
    return text.strip()


def _is_timeout_error(error: Exception) -> bool:
    """Recognize transport and Gemini API deadline errors without exposing them."""
    return (
        _provider_error_code(error) == 504
        or isinstance(error, TimeoutError)
        or error.__class__.__name__ in {
            "ConnectTimeout",
            "ReadTimeout",
            "TimeoutException",
        }
    )


def _provider_error_code(error: Exception) -> int | str | None:
    """Read the Google Gen AI APIError code when the provider supplies one."""
    code = getattr(error, "code", None)
    if code is None:
        response = getattr(error, "response", None)
        code = getattr(response, "status_code", None)
    return code if isinstance(code, (int, str)) else None


def _sanitize_provider_message(error: Exception, request: AssistantMessageRequest) -> str:
    """Produce bounded diagnostic text without secrets or learner context."""
    message = getattr(error, "message", None)
    if not isinstance(message, str) or not message.strip():
        message = str(error)

    for learner_value in (
        request.question,
        request.current_chunk.text,
        *(message.message for message in request.previous_messages),
    ):
        if learner_value:
            message = message.replace(learner_value, "[REDACTED_LEARNER_INPUT]")

    for pattern in _SECRET_PATTERNS:
        message = pattern.sub("[REDACTED_SECRET]", message)

    message = " ".join(message.split())
    return message[:MAX_DIAGNOSTIC_MESSAGE_LENGTH] or error.__class__.__name__


def _log_provider_failure(
    error: Exception,
    settings: AssistantSettings,
    request: AssistantMessageRequest,
) -> None:
    """Log safe provider diagnostics without logging prompts or credentials."""
    logger.error(
        "Gemini provider call failed: type=%s code=%s model=%s timeout_ms=%s message=%s",
        error.__class__.__name__,
        _provider_error_code(error),
        settings.gemini_model,
        settings.gemini_timeout_ms,
        _sanitize_provider_message(error, request),
    )


def create_gemini_response(
    request: AssistantMessageRequest,
    settings: AssistantSettings,
    client_factory: GeminiClientFactory = create_gemini_client,
) -> AssistantMessageResponse:
    """Send a separated learning prompt to Gemini and return its answer."""
    if not settings.gemini_api_key:
        raise AssistantConfigurationError("Gemini is not configured for this server.")

    emotion_signal = classify_conversational_signal(request.question)
    context = build_assistant_context(request, emotion_signal=emotion_signal)
    prompt = build_assistant_prompt(context)
    try:
        client = client_factory(settings.gemini_api_key, settings.gemini_timeout_ms)
        provider_response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        answer = _extract_response_text(provider_response)
    except AssistantProviderError as error:
        _log_provider_failure(error, settings, request)
        raise
    except Exception as error:
        _log_provider_failure(error, settings, request)
        if _is_timeout_error(error):
            raise AssistantProviderTimeoutError("The assistant provider timed out.") from error
        raise AssistantProviderError("The assistant provider is unavailable.") from error

    return _create_response(request, answer, emotion_signal)


def create_assistant_response(
    request: AssistantMessageRequest,
    settings: AssistantSettings | None = None,
    client_factory: GeminiClientFactory | None = None,
) -> AssistantMessageResponse:
    """Select local mock or real Gemini mode using centralized settings."""
    try:
        resolved_settings = settings or AssistantSettings.from_environment()
    except ConfigurationError as error:
        raise AssistantConfigurationError("The assistant service is misconfigured.") from error

    if resolved_settings.mode == "mock":
        return create_mock_response(request)
    return create_gemini_response(
        request,
        resolved_settings,
        client_factory or create_gemini_client,
    )

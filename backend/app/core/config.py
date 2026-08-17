"""Environment-backed configuration for the Adaptly backend."""

from dataclasses import dataclass
import os
from typing import Literal


DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_GEMINI_TIMEOUT_MS = 60_000
AssistantMode = Literal["mock", "gemini"]


class ConfigurationError(ValueError):
    """Raised when assistant environment settings are invalid."""


@dataclass(frozen=True)
class AssistantSettings:
    """Settings needed to select and call the assistant provider."""

    mode: AssistantMode
    gemini_api_key: str | None
    gemini_model: str
    gemini_timeout_ms: int

    @classmethod
    def from_environment(cls) -> "AssistantSettings":
        """Read assistant settings without logging any sensitive values."""
        mode = os.getenv("ASSISTANT_MODE", "mock").strip().lower()
        if mode not in {"mock", "gemini"}:
            raise ConfigurationError("ASSISTANT_MODE must be 'mock' or 'gemini'.")

        model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
        if not model:
            raise ConfigurationError("GEMINI_MODEL must not be blank.")

        timeout_value = os.getenv("GEMINI_TIMEOUT_MS", str(DEFAULT_GEMINI_TIMEOUT_MS))
        try:
            timeout_ms = int(timeout_value)
        except ValueError as error:
            raise ConfigurationError("GEMINI_TIMEOUT_MS must be an integer.") from error
        if timeout_ms <= 0 or timeout_ms > 120_000:
            raise ConfigurationError("GEMINI_TIMEOUT_MS must be between 1 and 120000.")

        api_key = os.getenv("GEMINI_API_KEY")
        return cls(
            mode=mode,
            gemini_api_key=api_key.strip() if api_key else None,
            gemini_model=model,
            gemini_timeout_ms=timeout_ms,
        )

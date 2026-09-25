"""Thin wrapper around the google-genai SDK for Module 8 insight reports (Issue #32).

The only place in Module 8 that imports ``google-genai`` — and that import is
lazy (inside the function body) so that test code, which always injects a
fake ``call_gemini`` callable instead of calling this module, never needs the
package importable, and a missing/misconfigured API key degrades to the
deterministic fallback instead of crashing the app at import time.

Deliberately standalone: Module 5's own Gemini usage lives only on an
unmerged, unreviewed branch (PR #43) with known problems (destructive router
rewrite, broken CORS, a conflicting pre-2.0 google-genai pin). This module
does not import anything from that branch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class GeminiUnavailableError(Exception):
    """Raised for every Gemini failure mode: no key, no package, network/service
    error, timeout, or an empty response. Callers catch this one type rather
    than several SDK-specific exceptions."""


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str | None
    model_name: str
    timeout_seconds: float


def load_gemini_config() -> GeminiConfig:
    """Read Gemini configuration from environment variables (see backend/.env.example).

    An unset ``GEMINI_API_KEY`` is a normal, expected state (e.g. local
    development without a key) — it is reported back as part of the config
    rather than raised here, so the caller can route straight to the
    deterministic fallback.
    """

    return GeminiConfig(
        api_key=os.environ.get("GEMINI_API_KEY") or None,
        model_name=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        timeout_seconds=float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "20")),
    )


def call_gemini(prompt: str, *, config: GeminiConfig | None = None) -> str:
    """Call Gemini once and return its raw text response.

    Raises ``GeminiUnavailableError`` for every failure mode so
    ``insights.generator`` has exactly one exception type to catch before
    falling back to the deterministic report.
    """

    resolved_config = config or load_gemini_config()
    if not resolved_config.api_key:
        raise GeminiUnavailableError("GEMINI_API_KEY is not configured.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise GeminiUnavailableError("google-genai package is not installed.") from error

    try:
        client = genai.Client(api_key=resolved_config.api_key)
        response = client.models.generate_content(
            model=resolved_config.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(
                    timeout=int(resolved_config.timeout_seconds * 1000)
                )
            ),
        )
    except Exception as error:  # network/timeout/service errors from the SDK
        raise GeminiUnavailableError(str(error)) from error

    text = getattr(response, "text", None)
    if not text:
        raise GeminiUnavailableError("Gemini returned an empty response.")
    return text

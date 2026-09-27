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
import time
from dataclasses import dataclass


class GeminiUnavailableError(Exception):
    """Raised for a *transient* Gemini failure: a timeout, a 5xx/429 response
    that outlasted :func:`call_gemini`'s own retries, another network/service
    error, or an empty response. ``insights.generator`` catches this (and its
    ``GeminiConfigurationError`` subclass below) as one type before falling
    back to the deterministic report, but the ``/insight-report/retry`` API
    route distinguishes the two by ``type(error).__name__`` (stored as the
    report's ``error_code``): a report that fell back for a reason raised as
    plain ``GeminiUnavailableError`` genuinely might succeed if retried later
    (Gemini was briefly unavailable), so the route allows a bounded number of
    retries for it."""


class GeminiConfigurationError(GeminiUnavailableError):
    """Raised when Gemini cannot be reached for a reason a retry cannot fix:
    no API key configured, the ``google-genai`` package not installed, or a
    non-transient 4xx response (bad key, bad model name — the same "every
    other 4xx is a misconfiguration" reasoning Module 4's ``provider.py``
    uses). The ``/insight-report/retry`` route refuses to retry a report
    whose stored ``error_code`` is this class's name, since nothing about
    retrying the same request changes the outcome."""


DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_SECONDS = 20.0

# Same retry shape as Module 4's app/intervention/provider.py: a 503 "high
# load" response is common enough to matter, and 429 is the free-tier rate
# limit rather than a mistake — both are worth a short, bounded retry before
# insights.generator gives up and falls back to the deterministic report.
# Every other 4xx is a bad key or a bad model name, so it fails fast instead.
RATE_LIMITED = 429
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)


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

    ``GEMINI_MODEL``/``GEMINI_TIMEOUT_SECONDS`` are guarded the same way
    Module 4's ``provider.py`` guards the variables it shares with this one:
    ``os.getenv(..., default)`` only falls back when a variable is *absent*,
    not when it's present-but-empty (e.g. a blank line in ``.env``, which is
    exactly the pattern ``.env.example`` documents for every optional key
    here). Left unguarded, a blank ``GEMINI_MODEL=`` line would silently ask
    Gemini for model ``""``, and a blank ``GEMINI_TIMEOUT_SECONDS=`` would
    raise inside ``float()`` and route every report to the fallback with no
    clearer evidence than an ``error_code`` buried in the stored document.
    """

    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    try:
        timeout_seconds = float(os.getenv("GEMINI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    return GeminiConfig(
        api_key=os.environ.get("GEMINI_API_KEY") or None,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
    )


def call_gemini(prompt: str, *, config: GeminiConfig | None = None) -> str:
    """Call Gemini and return its raw text response, retrying transient
    failures in-process before giving up.

    Raises ``GeminiConfigurationError`` (a ``GeminiUnavailableError``
    subclass) for failure modes a retry cannot fix — no key, no package, a
    non-transient 4xx — and plain ``GeminiUnavailableError`` for everything
    that might succeed on a later attempt: a timeout, a network error, an
    empty response, or a 5xx/429 that outlasted the ``MAX_ATTEMPTS`` retries
    below. ``insights.generator`` catches the common base type; the
    ``/insight-report/retry`` route reads the specific subclass name back out
    of the stored ``error_code`` to decide whether a later user-triggered
    retry is worth allowing.
    """

    resolved_config = config or load_gemini_config()
    if not resolved_config.api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured.")

    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as error:
        raise GeminiConfigurationError("google-genai package is not installed.") from error

    client = genai.Client(api_key=resolved_config.api_key)
    generation_config = types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=int(resolved_config.timeout_seconds * 1000))
    )

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.models.generate_content(
                model=resolved_config.model_name,
                contents=prompt,
                config=generation_config,
            )
        except errors.APIError as error:
            transient = isinstance(error, errors.ServerError) or (
                getattr(error, "code", None) == RATE_LIMITED
            )
            if not transient:
                raise GeminiConfigurationError(str(error)) from error
            last_error = error
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
            continue
        except Exception as error:  # network/timeout/other SDK errors
            raise GeminiUnavailableError(str(error)) from error

        text = getattr(response, "text", None)
        if not text:
            raise GeminiUnavailableError("Gemini returned an empty response.")
        return text

    raise GeminiUnavailableError(
        "Gemini was still unavailable after retrying."
    ) from last_error

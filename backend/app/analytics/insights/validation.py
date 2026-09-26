"""Validates Gemini's raw output before it is ever shown to a learner (Issue #32).

If validation fails for any reason, the caller (``generator.py``) falls back
to the deterministic report instead — an unvalidated Gemini response is never
persisted or returned, matching the design constraint that a Gemini failure
must never surface unsafe or misleading text.
"""

from __future__ import annotations

_PROHIBITED_TERMS = (
    "failure",
    "poor learner",
    "abnormal",
    "deficient",
    "inattentive",
    "lazy",
    "diagnosis",
    "disorder",
)

# Loose bounds around the ~150-word target the prompt asks for. Wide enough
# that a reasonable Gemini response never gets rejected on length alone, but
# tight enough to catch a degenerate one-line or wall-of-text response.
_MIN_WORDS = 40
_MAX_WORDS = 260

_MAX_STORED_LENGTH = 2000  # matches analytics-report.schema.json report_text.maxLength


class InvalidGeminiReportError(Exception):
    """Raised when Gemini's output fails validation and must not be shown to a learner."""


def validate_report_text(text: str | None) -> str:
    """Return ``text`` (stripped) if it passes validation, else raise.

    Checked, in order: non-empty, a plausible length, no prohibited clinical
    wording, and within the contract's stored-length limit.
    """

    if not text or not text.strip():
        raise InvalidGeminiReportError("Gemini returned an empty response.")

    stripped = text.strip()

    word_count = len(stripped.split())
    if word_count < _MIN_WORDS or word_count > _MAX_WORDS:
        raise InvalidGeminiReportError(
            f"Gemini response length ({word_count} words) is outside the expected range."
        )

    lowered = stripped.lower()
    for term in _PROHIBITED_TERMS:
        if term in lowered:
            raise InvalidGeminiReportError(
                f"Gemini response contains prohibited wording: '{term}'."
            )

    if len(stripped) > _MAX_STORED_LENGTH:
        raise InvalidGeminiReportError("Gemini response exceeds the maximum stored length.")

    return stripped

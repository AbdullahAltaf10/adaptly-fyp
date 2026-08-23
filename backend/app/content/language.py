"""
Language detection and content warnings.

Scope section 6.2 requires a warning when Urdu or low-confidence transcription
is detected. Section 7 explains why: Urdu and mixed Urdu-English (Roman Urdu)
transcribe poorly, and the system should say so rather than quietly produce a
bad study session.

Deliberately dependency-free. A full detector such as langdetect would be more
capable across many languages, but the requirement is specifically to spot Urdu
and to flag text this system cannot handle well — and that is decided by which
Unicode script the characters belong to, which needs no model.

Honest limitation: this identifies SCRIPT, not language. Urdu, Arabic, Persian
and Pashto share a script, so all four report as "ur". For the purpose here —
warning that the content is not English and will process poorly — that is
sufficient. Roman Urdu (Urdu written in Latin letters) is NOT detectable this
way and will read as English; that is called out in the warnings list.
"""

import unicodedata

LANGUAGE_UNKNOWN = "unknown"

# Warning codes. Kept as stable strings because they end up in the shared
# content contract's `warnings` array and other modules may key off them.
WARNING_NON_ENGLISH = "non_english_content"
WARNING_URDU = "urdu_content_reduced_accuracy"
WARNING_MIXED_SCRIPT = "mixed_script_content"
WARNING_LOW_CONFIDENCE_TRANSCRIPTION = "low_confidence_transcription"
WARNING_ROMAN_URDU_UNDETECTABLE = "roman_urdu_not_detectable"

# Proportion of letters in a script before we call the content that language.
_DOMINANT_THRESHOLD = 0.30
_MIXED_THRESHOLD = 0.10


def _script_of(char: str) -> str:
    """Which writing system a character belongs to, via its Unicode name."""
    try:
        name = unicodedata.name(char)
    except ValueError:
        return "OTHER"
    for script in ("ARABIC", "LATIN", "DEVANAGARI", "CYRILLIC", "HAN", "HIRAGANA", "KATAKANA", "HANGUL", "GREEK", "HEBREW"):
        if name.startswith(script):
            return script
    return "OTHER"


def _script_profile(text: str) -> dict:
    counts = {}
    total = 0
    for char in text:
        if not char.isalpha():
            continue
        total += 1
        script = _script_of(char)
        counts[script] = counts.get(script, 0) + 1
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def detect_language(text: str) -> str:
    """
    Best-effort language code for the shared contract's `language` field.

    Returns an ISO-639-1-style code, or "unknown". The contract keeps this
    field required, so "unknown" is the agreed placeholder rather than omitting
    it — that was settled during the contract review.
    """
    if not text or not text.strip():
        return LANGUAGE_UNKNOWN

    profile = _script_profile(text)
    if not profile:
        return LANGUAGE_UNKNOWN

    dominant = max(profile, key=profile.get)
    if profile[dominant] < _DOMINANT_THRESHOLD:
        return LANGUAGE_UNKNOWN

    return {
        "LATIN": "en",       # assumed; see the Roman Urdu caveat above
        "ARABIC": "ur",      # script-level: also Arabic/Persian/Pashto
        "DEVANAGARI": "hi",
        "CYRILLIC": "ru",
        "HAN": "zh",
        "HIRAGANA": "ja",
        "KATAKANA": "ja",
        "HANGUL": "ko",
        "GREEK": "el",
        "HEBREW": "he",
    }.get(dominant, LANGUAGE_UNKNOWN)


def build_warnings(text: str, language: str, *, is_transcription: bool = False) -> list:
    """
    Warnings for the shared contract's `warnings` array.

    Always returns a list. The contract keeps `warnings` required and expects an
    empty list when there is nothing to report — also settled during review.
    """
    warnings = []
    profile = _script_profile(text or "")

    if language == "ur":
        warnings.append(WARNING_URDU)
    elif language not in ("en", LANGUAGE_UNKNOWN):
        warnings.append(WARNING_NON_ENGLISH)

    # Two scripts both well represented, e.g. an Urdu article quoting English.
    significant = [s for s, share in profile.items() if share >= _MIXED_THRESHOLD and s != "OTHER"]
    if len(significant) > 1:
        warnings.append(WARNING_MIXED_SCRIPT)

    if is_transcription:
        # Automatic transcription is materially less reliable than text that was
        # typed, and Roman Urdu in particular is invisible to script detection.
        warnings.append(WARNING_LOW_CONFIDENCE_TRANSCRIPTION)
        if language == "en":
            warnings.append(WARNING_ROMAN_URDU_UNDETECTABLE)

    return warnings

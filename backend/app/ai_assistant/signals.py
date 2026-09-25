"""Lightweight, request-scoped conversational support signal classification."""

import re

from app.ai_assistant.schemas import EmotionSignal


_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9']+")
_FRUSTRATION_INDICATORS = (
    "frustrated",
    "frustrating",
    "annoying",
    "annoyed",
    "this is useless",
    "i've tried",
    "i have tried",
    "still not working",
    "again and again",
    "this makes no sense",
    "makes no sense",
)
_CONFUSION_INDICATORS = (
    "don't understand",
    "do not understand",
    "still don't get",
    "don't get this",
    "what does this mean",
    "confused",
    "confusing",
    "lost",
    "can you explain again",
    "explain that again",
    "explain this again",
    "i don't follow",
)


def normalize_learner_message(message: str) -> str:
    """Normalize case, apostrophes, whitespace, and basic punctuation for rules."""
    normalized = message.casefold().replace("’", "'").strip()
    return " ".join(_NON_ALPHANUMERIC.sub(" ", normalized).split())


def _indicator_score(message: str, indicators: tuple[str, ...]) -> int:
    """Count normalized phrase matches without retaining or storing the message."""
    padded_message = f" {message} "
    return sum(f" {indicator} " in padded_message for indicator in indicators)


def classify_conversational_signal(message: str) -> EmotionSignal:
    """Classify the current message only: frustration > confusion > neutral.

    Frustration takes precedence because it is the stronger escalation signal
    for a future downstream support layer. This is not clinical emotion
    recognition and does not persist or profile learner information.
    """
    normalized = normalize_learner_message(message)
    if _indicator_score(normalized, _FRUSTRATION_INDICATORS):
        return "frustration"
    if _indicator_score(normalized, _CONFUSION_INDICATORS):
        return "confusion"
    return "neutral"

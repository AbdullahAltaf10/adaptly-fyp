"""Deterministic, non-Gemini insight report (Issue #32).

Used whenever Gemini is unavailable, times out, has no API key configured,
or returns a response that fails validation. Built entirely from the same
validated session summary the Gemini prompt uses — no network call, and
nothing invented beyond what the summary already says. Per CLAUDE.md 6.5,
"unknown is not zero": a missing value here is described as unmeasured, never
silently treated as zero, focused, or a failure.
"""

from __future__ import annotations

from typing import Any


def _format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = round(seconds)
    minutes, secs = divmod(total, 60)
    if minutes == 0:
        return f"{secs} second{'s' if secs != 1 else ''}"
    if secs == 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{minutes} minute{'s' if minutes != 1 else ''} and {secs} second{'s' if secs != 1 else ''}"


def build_fallback_report(summary: dict[str, Any]) -> str:
    duration = _format_duration(summary.get("duration_seconds"))
    chunks = summary.get("chunks_completed")
    longest = summary.get("longest_focused_period")
    longest_text = _format_duration(longest["duration_seconds"]) if longest else None

    intervention_metrics = summary.get("intervention_metrics") or {}
    total_support = intervention_metrics.get("total_count") or 0
    effective_support = intervention_metrics.get("effective_count") or 0

    recovery = summary.get("recovery_metrics") or {}
    recovery_rate = recovery.get("recovery_rate")

    quality = summary.get("data_quality") or {}
    sufficient = quality.get("has_sufficient_data", True)

    sentences: list[str] = []

    if duration:
        opener = f"You spent {duration} on this session"
        opener += f", completing {chunks} section{'s' if chunks != 1 else ''}." if chunks else "."
        sentences.append(opener)
    else:
        sentences.append(
            "Here is a summary of this session based on the information that was collected."
        )

    if not sufficient:
        sentences.append(
            "There wasn't enough engagement data collected this time to give a "
            "detailed picture, but here is what we could tell from what was recorded."
        )

    if longest_text:
        sentences.append(f"Your longest focused stretch lasted about {longest_text}.")
    elif sufficient:
        sentences.append(
            "A single longest focused period could not be identified from the data collected."
        )

    if total_support == 0:
        sentences.append(
            "No extra support was offered during this session — you were on track throughout."
        )
    else:
        support_sentence = (
            f"Support was offered {total_support} time{'s' if total_support != 1 else ''} "
            "during this session"
        )
        if effective_support:
            support_sentence += (
                f", and it seemed to help {effective_support} of those "
                f"time{'s' if effective_support != 1 else ''}."
            )
        else:
            support_sentence += ", and whether it helped could not always be determined."
        sentences.append(support_sentence)

        if recovery_rate is not None:
            sentences.append(
                f"Overall, focus returned after support about {round(recovery_rate * 100)}% of the time."
            )

    sentences.append(
        "Consider revisiting any sections that felt difficult next time, and keep using "
        "the support tools available if you'd like extra help along the way."
    )

    return " ".join(sentences)

"""Builds the Gemini prompt from a validated Module 8 session summary (Issue #32).

Deliberately pure and kept separate from metric calculation, database access,
API routing, and frontend code — this module only ever receives an
already-computed ``session-summary.schema.json``-shaped dict. It never
receives raw events, chat transcripts, or webcam-derived data (see CLAUDE.md
6.4/6.5); there is nothing in this file capable of sending any of that to
Gemini even by accident, since it only reads the aggregate fields below.
"""

from __future__ import annotations

from typing import Any

_INSTRUCTIONS = """You are writing a short, supportive summary of a learner's study session, for the learner themself to read afterward.

Stay strictly grounded in the session data provided below. Do not invent events, scores, or outcomes that are not in the data. Do not use clinical or diagnostic language such as "failure", "poor learner", "abnormal", "deficient", or "inattentive". Never compare this learner to other learners. Never claim that a support action worked if its outcome is listed as unknown or not observed.

Write approximately 150 words (between 130 and 170), in a warm, encouraging, and calm tone. Mention: something that went well, where difficulty appeared if any did, which kinds of support were offered and whether they seemed to help (only when the data says so), and one supportive, low-pressure suggestion for what the learner might revisit next. If the data is limited or incomplete, say so plainly rather than guessing."""


def build_prompt(summary: dict[str, Any]) -> str:
    lines = [_INSTRUCTIONS, "", "Session data:"]
    lines.append(f"- Duration: {summary.get('duration_seconds')} seconds")
    lines.append(f"- Sections completed: {summary.get('chunks_completed')}")

    distribution = summary.get("engagement_distribution") or {}
    for state in ("focused", "drifting", "struggling", "fatigued", "recovered", "unknown"):
        measure = distribution.get(state) or {}
        lines.append(
            f"- Engagement state '{state}': "
            f"{measure.get('duration_seconds')} seconds ({measure.get('percentage')}%)"
        )

    longest = summary.get("longest_focused_period")
    if longest:
        lines.append(f"- Longest focused period: {longest.get('duration_seconds')} seconds")
    else:
        lines.append("- Longest focused period: could not be determined")

    intervention_metrics = summary.get("intervention_metrics") or {}
    lines.append(
        "- Support offered: "
        f"{intervention_metrics.get('total_count', 0)} time(s); "
        f"helped {intervention_metrics.get('effective_count', 0)}; "
        f"did not help {intervention_metrics.get('ineffective_count', 0)}; "
        f"outcome unknown {intervention_metrics.get('unknown_outcome_count', 0)}"
    )
    for item in intervention_metrics.get("by_type", []) or []:
        lines.append(
            f"  - {item.get('intervention_type')}: used {item.get('total_count')} time(s), "
            f"effectiveness rate {item.get('effectiveness_rate')}"
        )

    recovery = summary.get("recovery_metrics") or {}
    lines.append(
        "- Recovery: "
        f"rate {recovery.get('recovery_rate')}, "
        f"average recovery time {recovery.get('average_recovery_time_seconds')} seconds"
    )

    assistant = summary.get("assistant_usage") or {}
    lines.append(f"- Assistant interactions: {assistant.get('total_event_count', 0)}")

    critical = summary.get("critical_section_engagement") or {}
    lines.append(
        "- Critical-section engagement: "
        f"{critical.get('engaged_section_count', 0)} of "
        f"{critical.get('critical_section_count', 0)} sections engaged"
    )

    quality = summary.get("data_quality") or {}
    lines.append(
        "- Data quality: "
        f"sufficient data = {quality.get('has_sufficient_data')}, "
        f"flags = {quality.get('flags')}"
    )

    return "\n".join(lines)

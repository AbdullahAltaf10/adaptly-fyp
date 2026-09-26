"""Pure Module 10 critical-section attestation evidence (Issue #73).

Reuses the exact same critical-chunk lookup Module 8's own
``metrics.py::_critical_section_metrics`` uses: a chunk is critical when its
chunk-context record has ``is_critical: true``. This module does not invent
a second, parallel notion of "critical" -- Module 8 and Module 10 must never
disagree about which chunks matter.

Takes a session summary's ``timeline_segments`` (Issue #26 output), the same
``chunk_context`` shape Module 8's finalization service already builds
(``{"chunk_id", "is_critical", "completed"}``), and a session's raw
intervention events (for per-chunk intervention counts, which the summary
does not retain individually). Deliberately does not import MongoDB,
FastAPI, or anything from ``backend/app/compliance/persistence`` -- the
caller (Issue #74's service layer) is responsible for fetching intervention
events from Module 8's own ``InterventionEventRepository`` and passing them
in here as plain mappings, the same way Module 8's ``finalize_session``
passes already-fetched events into its own pure metric engine.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

POSITIVE_STATES = frozenset({"focused", "recovered"})
DIFFICULTY_STATES = frozenset({"drifting", "struggling", "fatigued"})


def _critical_chunk_ids(chunk_context: Sequence[Mapping[str, Any]] | None) -> set[str]:
    return {
        chunk["chunk_id"]
        for chunk in (chunk_context or ())
        if chunk.get("is_critical") is True and chunk.get("chunk_id") is not None
    }


def _verdict_for_known_states(known_states: Sequence[str]) -> str:
    difficulty_indices = [
        index for index, state in enumerate(known_states) if state in DIFFICULTY_STATES
    ]
    if not difficulty_indices:
        return "sustained_engagement"
    first_difficulty = difficulty_indices[0]
    later_positive = any(
        state in POSITIVE_STATES for state in known_states[first_difficulty + 1 :]
    )
    return "difficulty_then_recovered" if later_positive else "difficulty_not_recovered"


def _evidence_for_chunk(
    chunk_id: str,
    timeline_segments: Sequence[Mapping[str, Any]],
    intervention_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    chunk_segments = [
        segment for segment in timeline_segments if segment.get("chunk_id") == chunk_id
    ]
    intervention_count = sum(
        1 for event in intervention_events if event.get("chunk_id") == chunk_id
    )

    if not chunk_segments:
        return {
            "chunk_id": chunk_id,
            "verdict": "not_reached",
            "focused_seconds": 0.0,
            "difficulty_seconds": 0.0,
            "intervention_count": intervention_count,
            "first_seen_at": None,
            "last_seen_at": None,
        }

    known_segments = [
        segment for segment in chunk_segments if segment.get("state") != "unknown"
    ]
    focused_seconds = sum(
        float(segment.get("duration_seconds", 0.0))
        for segment in chunk_segments
        if segment.get("state") in POSITIVE_STATES
    )
    difficulty_seconds = sum(
        float(segment.get("duration_seconds", 0.0))
        for segment in chunk_segments
        if segment.get("state") in DIFFICULTY_STATES
    )
    first_seen_at = chunk_segments[0]["started_at"]
    last_seen_at = chunk_segments[-1]["ended_at"]

    if not known_segments:
        verdict = "insufficient_data"
    else:
        verdict = _verdict_for_known_states(
            [segment["state"] for segment in known_segments]
        )

    return {
        "chunk_id": chunk_id,
        "verdict": verdict,
        "focused_seconds": round(focused_seconds, 6),
        "difficulty_seconds": round(difficulty_seconds, 6),
        "intervention_count": intervention_count,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
    }


def build_critical_section_evidence(
    timeline_segments: Sequence[Mapping[str, Any]],
    chunk_context: Sequence[Mapping[str, Any]] | None,
    intervention_events: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return one evidence entry per critical chunk, in chunk-context order.

    Empty ``chunk_context`` (or no chunk flagged ``is_critical``) returns an
    empty list -- the expected, normal result for every real session today,
    since Module 9 (which sets ``is_critical``) does not exist yet.
    """

    critical_ids = _critical_chunk_ids(chunk_context)
    if not critical_ids:
        return []

    # Preserve chunk_context's own order rather than set iteration order, so
    # output is deterministic across runs.
    ordered_ids = [
        chunk["chunk_id"]
        for chunk in chunk_context
        if chunk.get("chunk_id") in critical_ids
    ]
    # De-duplicate while preserving order, in case chunk_context ever repeats
    # an id (e.g. a progress-tracking record updated more than once).
    seen: set[str] = set()
    deduplicated_ids = []
    for chunk_id in ordered_ids:
        if chunk_id not in seen:
            seen.add(chunk_id)
            deduplicated_ids.append(chunk_id)

    return [
        _evidence_for_chunk(chunk_id, timeline_segments, intervention_events)
        for chunk_id in deduplicated_ids
    ]

"""Allowed storage fields per collection, mirrored from ``shared/contracts/``.

Every write path filters incoming documents through these sets before they
reach MongoDB. This is a defense-in-depth privacy guard: even if a caller
accidentally attaches a webcam frame, dense landmark blob, or chat transcript
to an event payload, it is silently dropped rather than persisted. The
contracts are authoritative for what belongs in each event; this module does
not add or redesign fields, it only mirrors the existing schemas.
"""

from __future__ import annotations

SESSION_FIELDS = {
    "schema_version",
    "session_id",
    "user_id",
    "content_id",
    "status",
    "current_chunk_id",
    "started_at",
    "ended_at",
    "duration_seconds",
    "webcam_enabled",
    "voice_input_enabled",
    "voice_output_enabled",
    "intervention_count",
    "assistant_message_count",
    "created_at",
    "updated_at",
}

ENGAGEMENT_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "session_id",
    "user_id",
    "content_id",
    "chunk_id",
    "timestamp",
    "state",
    "confidence",
    "gaze_x",
    "gaze_y",
    "blink_rate",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "eye_openness",
    "brow_raise",
    "inter_brow",
    "gaze_regression_detected",
    "deep_thinking_detected",
    "source",
}

INTERVENTION_EVENT_FIELDS = {
    "schema_version",
    "intervention_id",
    "session_id",
    "user_id",
    "content_id",
    "chunk_id",
    "timestamp",
    "intervention_type",
    "reason",
    "reason_code",
    "triggering_engagement_state",
    "triggering_engagement_event_id",
    "delivery_status",
    "outcome",
    "recovery_timestamp",
    "recovery_duration_seconds",
    "helped",
    "policy_version",
    "model_version",
}

ASSISTANT_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "session_id",
    "user_id",
    "content_id",
    "chunk_id",
    "timestamp",
    "direction",
    "input_mode",
    "response_mode",
    "intent",
    "learner_signal",
    "suggested_question_used",
    "status",
    "error_code",
    "model_name",
    "model_version",
}

# Session-summary contract fields (shared/contracts/session-summary.schema.json).
# Stored verbatim under the "summary" key of a session-analytics document; see
# session_analytics.py for the persistence envelope around it.
SESSION_SUMMARY_FIELDS = {
    "schema_version",
    "metric_version",
    "session_id",
    "user_id",
    "content_id",
    "duration_seconds",
    "completed_at",
    "computed_at",
    "engagement_distribution",
    "timeline_segments",
    "longest_focused_period",
    "intervention_metrics",
    "recovery_metrics",
    "assistant_usage",
    "critical_section_engagement",
    "chunks_completed",
    "data_quality",
}

# Chunk progress has no shared contract yet (Issue #27 asks only for
# persistence support). Kept intentionally minimal, matching the issue's
# "Chunk Progress" data-area list exactly.
CHUNK_PROGRESS_FIELDS = {
    "session_id",
    "content_id",
    "chunk_id",
    "entered_at",
    "completed_at",
    "status",
    "is_critical",
}

LEARNING_PROFILE_FIELDS = {
    "schema_version",
    "metric_version",
    "user_id",
    "sessions_analyzed",
    "analysis_date_range",
    "average_session_duration_seconds",
    "average_focus_percentage",
    "focus_trend",
    "recovery_trend",
    "intervention_effectiveness_by_type",
    "assistant_usage_patterns",
    "recurring_difficulty_areas",
    "effective_support_methods",
    "critical_section_aggregates",
    "data_quality",
    "computed_at",
}


def filtered(document: dict, allowed_fields: set[str]) -> dict:
    """Return a copy of ``document`` containing only allow-listed keys."""

    return {key: value for key, value in document.items() if key in allowed_fields}

/**
 * Contract-valid mock analytics data for the Module 8 dashboard (Issue #30).
 *
 * Every `summary` object below matches shared/contracts/session-summary.schema.json
 * exactly (same required fields, same null-vs-zero rules — see CLAUDE.md 6.5:
 * "unknown is not zero"). `overview` and `insightReport` are the two small
 * additions the real backend API is expected to layer on top of that
 * contract for display purposes, matching the precedent already set by the
 * real `GET /api/sessions/{id}/analytics` endpoint (Issue #29), which wraps
 * the same contract in an `insight_report` envelope field. `insightReport`
 * here is the display-relevant subset of
 * shared/contracts/analytics-report.schema.json (`status` and `report_text`).
 *
 * This file is the ONLY thing that needs to change when the real API
 * replaces mock data — see `useSessionAnalytics.js`.
 */

const SCHEMA_VERSION = "1.0";
const METRIC_VERSION = "1.0";

const BASE_TIME_MS = Date.UTC(2026, 7, 17, 9, 0, 0);

function isoAt(offsetSeconds) {
  return new Date(BASE_TIME_MS + offsetSeconds * 1000).toISOString();
}

function measure(durationSeconds, percentage) {
  return { duration_seconds: durationSeconds, percentage };
}

function fullDistribution(overrides) {
  const zero = measure(0, 0);
  return {
    focused: zero,
    drifting: zero,
    struggling: zero,
    fatigued: zero,
    recovered: zero,
    unknown: zero,
    ...overrides,
  };
}

function segment(startOffset, endOffset, state, chunkId = "chunk-1") {
  return {
    started_at: isoAt(startOffset),
    ended_at: isoAt(endOffset),
    duration_seconds: endOffset - startOffset,
    state,
    average_confidence: state === "unknown" ? null : 0.88,
    chunk_id: state === "unknown" ? null : chunkId,
  };
}

function zeroInterventionMetrics() {
  return {
    total_count: 0,
    effective_count: 0,
    ineffective_count: 0,
    unknown_outcome_count: 0,
    effectiveness_rate: null,
    by_type: [],
  };
}

function zeroAssistantUsage() {
  return {
    total_event_count: 0,
    learner_message_count: 0,
    assistant_message_count: 0,
    typed_input_count: 0,
    voice_input_count: 0,
    suggested_question_count: 0,
    text_response_count: 0,
    voice_response_count: 0,
    successful_interaction_count: 0,
    error_count: 0,
  };
}

// --- Scenario 1: a normal, mostly-fine completed session -------------------
const NORMAL_COMPLETED_SESSION = {
  overview: {
    content_title: "Intro to Cellular Respiration",
    session_status: "completed",
  },
  summary: {
    schema_version: SCHEMA_VERSION,
    metric_version: METRIC_VERSION,
    session_id: "session-normal",
    user_id: "user-1",
    content_id: "content-1",
    duration_seconds: 1200,
    completed_at: isoAt(1200),
    computed_at: isoAt(1200),
    engagement_distribution: fullDistribution({
      focused: measure(840, 70),
      drifting: measure(120, 10),
      struggling: measure(120, 10),
      recovered: measure(60, 5),
      unknown: measure(60, 5),
    }),
    timeline_segments: [
      segment(0, 840, "focused"),
      segment(840, 960, "drifting"),
      segment(960, 1080, "struggling"),
      segment(1080, 1140, "recovered"),
      segment(1140, 1200, "unknown"),
    ],
    longest_focused_period: {
      started_at: isoAt(0),
      ended_at: isoAt(840),
      duration_seconds: 840,
      chunk_id: "chunk-1",
    },
    intervention_metrics: {
      total_count: 1,
      effective_count: 1,
      ineffective_count: 0,
      unknown_outcome_count: 0,
      effectiveness_rate: 1,
      by_type: [
        {
          intervention_type: "break_suggestion",
          total_count: 1,
          effective_count: 1,
          ineffective_count: 0,
          unknown_outcome_count: 0,
          effectiveness_rate: 1,
        },
      ],
    },
    recovery_metrics: {
      eligible_intervention_count: 1,
      recovered_intervention_count: 1,
      recovery_rate: 1,
      average_recovery_time_seconds: 60,
    },
    assistant_usage: {
      total_event_count: 2,
      learner_message_count: 1,
      assistant_message_count: 1,
      typed_input_count: 1,
      voice_input_count: 0,
      suggested_question_count: 0,
      text_response_count: 1,
      voice_response_count: 0,
      successful_interaction_count: 1,
      error_count: 0,
    },
    critical_section_engagement: {
      critical_section_count: 2,
      engaged_section_count: 2,
      engagement_rate: 1,
      focused_duration_seconds: 400,
    },
    chunks_completed: 4,
    data_quality: {
      has_sufficient_data: true,
      event_coverage_rate: 0.95,
      unknown_duration_seconds: 60,
      flags: [],
    },
  },
  insightReport: {
    status: "generated",
    report_text:
      "You spent most of this session focused, with a short dip partway through that you recovered from after a suggested break. Nice work sticking with the material.",
  },
};

// --- Scenario 2: no interventions were offered ------------------------------
const NO_INTERVENTIONS = {
  overview: {
    content_title: "Reading: Photosynthesis Basics",
    session_status: "completed",
  },
  summary: {
    schema_version: SCHEMA_VERSION,
    metric_version: METRIC_VERSION,
    session_id: "session-no-interventions",
    user_id: "user-1",
    content_id: "content-2",
    duration_seconds: 600,
    completed_at: isoAt(600),
    computed_at: isoAt(600),
    engagement_distribution: fullDistribution({
      focused: measure(540, 90),
      unknown: measure(60, 10),
    }),
    timeline_segments: [segment(0, 540, "focused"), segment(540, 600, "unknown")],
    longest_focused_period: {
      started_at: isoAt(0),
      ended_at: isoAt(540),
      duration_seconds: 540,
      chunk_id: "chunk-1",
    },
    intervention_metrics: zeroInterventionMetrics(),
    recovery_metrics: {
      eligible_intervention_count: 0,
      recovered_intervention_count: 0,
      recovery_rate: null,
      average_recovery_time_seconds: null,
    },
    assistant_usage: zeroAssistantUsage(),
    critical_section_engagement: {
      critical_section_count: 1,
      engaged_section_count: 1,
      engagement_rate: 1,
      focused_duration_seconds: 300,
    },
    chunks_completed: 3,
    data_quality: {
      has_sufficient_data: true,
      event_coverage_rate: 0.9,
      unknown_duration_seconds: 60,
      flags: [],
    },
  },
  insightReport: {
    status: "generated",
    report_text:
      "You stayed focused for the whole session and didn't need any extra support along the way.",
  },
};

// --- Scenario 3: sparse data — most of the session is unmeasured ----------
const SPARSE_ANALYTICS_DATA = {
  overview: {
    content_title: "Video: The Water Cycle",
    session_status: "completed",
  },
  summary: {
    schema_version: SCHEMA_VERSION,
    metric_version: METRIC_VERSION,
    session_id: "session-sparse",
    user_id: "user-1",
    content_id: "content-3",
    duration_seconds: 900,
    completed_at: isoAt(900),
    computed_at: isoAt(900),
    engagement_distribution: fullDistribution({
      focused: measure(150, 17),
      unknown: measure(750, 83),
    }),
    timeline_segments: [segment(0, 150, "focused"), segment(150, 900, "unknown")],
    longest_focused_period: {
      started_at: isoAt(0),
      ended_at: isoAt(150),
      duration_seconds: 150,
      chunk_id: "chunk-1",
    },
    intervention_metrics: zeroInterventionMetrics(),
    recovery_metrics: {
      eligible_intervention_count: 0,
      recovered_intervention_count: 0,
      recovery_rate: null,
      average_recovery_time_seconds: null,
    },
    assistant_usage: zeroAssistantUsage(),
    critical_section_engagement: {
      critical_section_count: 0,
      engaged_section_count: 0,
      engagement_rate: null,
      focused_duration_seconds: 0,
    },
    chunks_completed: 1,
    data_quality: {
      has_sufficient_data: false,
      event_coverage_rate: 0.17,
      unknown_duration_seconds: 750,
      flags: ["sparse_engagement", "excessive_unknown_gaps"],
    },
  },
  insightReport: {
    status: "fallback_generated",
    report_text:
      "There wasn't enough engagement data collected this session to give a detailed summary, but here's what we could tell: you were reading for about 15 minutes.",
  },
};

// --- Scenario 4: no webcam data was collected at all -----------------------
const NO_WEBCAM_DATA = {
  overview: {
    content_title: "Article: Newton's Laws of Motion",
    session_status: "completed",
  },
  summary: {
    schema_version: SCHEMA_VERSION,
    metric_version: METRIC_VERSION,
    session_id: "session-no-webcam",
    user_id: "user-1",
    content_id: "content-4",
    duration_seconds: 720,
    completed_at: isoAt(720),
    computed_at: isoAt(720),
    engagement_distribution: fullDistribution({ unknown: measure(720, 100) }),
    timeline_segments: [segment(0, 720, "unknown")],
    longest_focused_period: null,
    intervention_metrics: zeroInterventionMetrics(),
    recovery_metrics: {
      eligible_intervention_count: 0,
      recovered_intervention_count: 0,
      recovery_rate: null,
      average_recovery_time_seconds: null,
    },
    assistant_usage: {
      ...zeroAssistantUsage(),
      total_event_count: 2,
      learner_message_count: 1,
      assistant_message_count: 1,
      typed_input_count: 1,
      text_response_count: 1,
      successful_interaction_count: 1,
    },
    critical_section_engagement: {
      critical_section_count: 1,
      engaged_section_count: 0,
      engagement_rate: 0,
      focused_duration_seconds: 0,
    },
    chunks_completed: 2,
    data_quality: {
      has_sufficient_data: false,
      event_coverage_rate: 0,
      unknown_duration_seconds: 720,
      flags: ["no_webcam_data", "sparse_engagement"],
    },
  },
  insightReport: {
    status: "fallback_generated",
    report_text:
      "No camera-based engagement data was available for this session, but you did use the assistant once to ask a question while reading.",
  },
};

// --- Scenario 5: the AI insight report failed to generate ------------------
const INSIGHT_REPORT_UNAVAILABLE = {
  overview: {
    content_title: "Reading: The French Revolution",
    session_status: "completed",
  },
  summary: {
    schema_version: SCHEMA_VERSION,
    metric_version: METRIC_VERSION,
    session_id: "session-insight-unavailable",
    user_id: "user-1",
    content_id: "content-5",
    duration_seconds: 1500,
    completed_at: isoAt(1500),
    computed_at: isoAt(1500),
    engagement_distribution: fullDistribution({
      focused: measure(1200, 80),
      drifting: measure(180, 12),
      unknown: measure(120, 8),
    }),
    timeline_segments: [
      segment(0, 1200, "focused"),
      segment(1200, 1380, "drifting"),
      segment(1380, 1500, "unknown"),
    ],
    longest_focused_period: {
      started_at: isoAt(0),
      ended_at: isoAt(1200),
      duration_seconds: 1200,
      chunk_id: "chunk-1",
    },
    intervention_metrics: {
      total_count: 2,
      effective_count: 1,
      ineffective_count: 0,
      unknown_outcome_count: 1,
      effectiveness_rate: 1,
      by_type: [
        {
          intervention_type: "simplify_content",
          total_count: 1,
          effective_count: 1,
          ineffective_count: 0,
          unknown_outcome_count: 0,
          effectiveness_rate: 1,
        },
        {
          intervention_type: "assistant_help_prompt",
          total_count: 1,
          effective_count: 0,
          ineffective_count: 0,
          unknown_outcome_count: 1,
          effectiveness_rate: null,
        },
      ],
    },
    recovery_metrics: {
      eligible_intervention_count: 2,
      recovered_intervention_count: 1,
      recovery_rate: 0.5,
      average_recovery_time_seconds: 45,
    },
    assistant_usage: {
      total_event_count: 2,
      learner_message_count: 1,
      assistant_message_count: 1,
      typed_input_count: 1,
      voice_input_count: 0,
      suggested_question_count: 0,
      text_response_count: 1,
      voice_response_count: 0,
      successful_interaction_count: 1,
      error_count: 0,
    },
    critical_section_engagement: {
      critical_section_count: 3,
      engaged_section_count: 3,
      engagement_rate: 1,
      focused_duration_seconds: 900,
    },
    chunks_completed: 5,
    data_quality: {
      has_sufficient_data: true,
      event_coverage_rate: 0.92,
      unknown_duration_seconds: 120,
      flags: [],
    },
  },
  insightReport: {
    status: "failed",
    report_text: null,
  },
};

// --- Scenario 6: everything present, nothing missing ------------------------
const COMPLETE_ANALYTICS = {
  overview: {
    content_title: "Chapter 4: Supply and Demand",
    session_status: "completed",
  },
  summary: {
    schema_version: SCHEMA_VERSION,
    metric_version: METRIC_VERSION,
    session_id: "session-complete",
    user_id: "user-1",
    content_id: "content-6",
    duration_seconds: 1800,
    completed_at: isoAt(1800),
    computed_at: isoAt(1800),
    engagement_distribution: fullDistribution({
      focused: measure(1620, 90),
      recovered: measure(180, 10),
    }),
    timeline_segments: [segment(0, 1620, "focused"), segment(1620, 1800, "recovered")],
    longest_focused_period: {
      started_at: isoAt(0),
      ended_at: isoAt(1620),
      duration_seconds: 1620,
      chunk_id: "chunk-1",
    },
    intervention_metrics: {
      total_count: 1,
      effective_count: 1,
      ineffective_count: 0,
      unknown_outcome_count: 0,
      effectiveness_rate: 1,
      by_type: [
        {
          intervention_type: "bullet_summary",
          total_count: 1,
          effective_count: 1,
          ineffective_count: 0,
          unknown_outcome_count: 0,
          effectiveness_rate: 1,
        },
      ],
    },
    recovery_metrics: {
      eligible_intervention_count: 1,
      recovered_intervention_count: 1,
      recovery_rate: 1,
      average_recovery_time_seconds: 30,
    },
    assistant_usage: {
      total_event_count: 4,
      learner_message_count: 2,
      assistant_message_count: 2,
      typed_input_count: 1,
      voice_input_count: 1,
      suggested_question_count: 1,
      text_response_count: 2,
      voice_response_count: 0,
      successful_interaction_count: 2,
      error_count: 0,
    },
    critical_section_engagement: {
      critical_section_count: 4,
      engaged_section_count: 4,
      engagement_rate: 1,
      focused_duration_seconds: 1200,
    },
    chunks_completed: 6,
    data_quality: {
      has_sufficient_data: true,
      event_coverage_rate: 1,
      unknown_duration_seconds: 0,
      flags: [],
    },
  },
  insightReport: {
    status: "generated",
    report_text:
      "This was a strong, focused session from start to finish. A quick summary partway through helped you settle back in, and you used the assistant twice to check your understanding.",
  },
};

export const MOCK_SCENARIOS = {
  NORMAL_COMPLETED_SESSION,
  NO_INTERVENTIONS,
  SPARSE_ANALYTICS_DATA,
  NO_WEBCAM_DATA,
  INSIGHT_REPORT_UNAVAILABLE,
  COMPLETE_ANALYTICS,
};

const MOCK_SESSIONS_BY_ID = Object.fromEntries(
  Object.values(MOCK_SCENARIOS).map((scenario) => [scenario.summary.session_id, scenario])
);

/** Sentinel ids a caller can use to deliberately exercise an error path. */
export const MOCK_ERROR_SESSION_IDS = {
  SUMMARY_MISSING: "session-summary-missing",
  SERVER_ERROR: "session-server-error",
};

const MOCK_NETWORK_DELAY_MS = 30;

/**
 * The mock stand-in for `GET /api/sessions/{session_id}/analytics`.
 *
 * Resolves with `{ overview, summary, insightReport }` for a known mock
 * session, or rejects with an `Error` carrying a `.kind` field
 * ("not_found" | "summary_missing" | "server_error") — the same shape
 * `classifyError` in `src/api/client.js` produces for real requests, so
 * `ErrorState` and this function's real replacement can share one contract.
 */
export function fetchMockSessionAnalytics(sessionId) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (sessionId === MOCK_ERROR_SESSION_IDS.SUMMARY_MISSING) {
        const error = new Error("Analytics summary not yet computed.");
        error.kind = "summary_missing";
        reject(error);
        return;
      }
      if (sessionId === MOCK_ERROR_SESSION_IDS.SERVER_ERROR) {
        const error = new Error("Mock server error.");
        error.kind = "server_error";
        reject(error);
        return;
      }
      const scenario = MOCK_SESSIONS_BY_ID[sessionId];
      if (!scenario) {
        const error = new Error(`No mock session found for "${sessionId}".`);
        error.kind = "not_found";
        reject(error);
        return;
      }
      resolve(scenario);
    }, MOCK_NETWORK_DELAY_MS);
  });
}

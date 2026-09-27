/**
 * Contract-valid mock compliance reports, for developing and testing the
 * views before wiring in the real endpoints (mirrors Module 8's own
 * `src/analytics/mockData.js` pattern).
 */

export const MOCK_COMPLETE_REPORT = {
  schema_version: "1.0",
  score_version: "1.0",
  report_id: "report-session-1",
  session_id: "session-1",
  user_id: "user-1",
  content_id: "content-1",
  generated_at: "2026-08-17T09:05:00Z",
  source_summary: { metric_version: "1.0", computed_at: "2026-08-17T09:05:00Z" },
  status: "complete",
  engagement_quality_score: 78,
  components: [
    {
      key: "attentional_presence",
      score: 80,
      weight: 0.25,
      weight_applied: 0.25,
      status: "included",
      reason: null,
    },
    {
      key: "critical_section_engagement",
      score: null,
      weight: 0.25,
      weight_applied: 0,
      status: "not_applicable",
      reason: "No critical sections were tagged for this session.",
    },
    {
      key: "recovery_rate",
      score: 75,
      weight: 0.25,
      weight_applied: 0.375,
      status: "included",
      reason: null,
    },
    {
      key: "chatbot_engagement",
      score: 80,
      weight: 0.25,
      weight_applied: 0.375,
      status: "included",
      reason: null,
    },
  ],
  excluded_components: [
    {
      key: "critical_section_engagement",
      reason: "No critical sections were tagged for this session.",
    },
  ],
  critical_sections: [],
  data_quality: {
    has_sufficient_data: true,
    event_coverage_rate: 0.92,
    unknown_duration_seconds: 12,
    flags: [],
  },
};

export const MOCK_INSUFFICIENT_DATA_REPORT = {
  ...MOCK_COMPLETE_REPORT,
  report_id: "report-session-2",
  session_id: "session-2",
  status: "insufficient_data",
  engagement_quality_score: null,
  components: MOCK_COMPLETE_REPORT.components.map((component) => ({
    ...component,
    weight_applied: 0,
  })),
  data_quality: { ...MOCK_COMPLETE_REPORT.data_quality, has_sufficient_data: false, flags: ["sparse_engagement"] },
};

export const MOCK_REPORT_WITH_CRITICAL_SECTIONS = {
  ...MOCK_COMPLETE_REPORT,
  report_id: "report-session-3",
  session_id: "session-3",
  critical_sections: [
    {
      chunk_id: "chunk-1",
      verdict: "sustained_engagement",
      focused_seconds: 120,
      difficulty_seconds: 0,
      intervention_count: 0,
      first_seen_at: "2026-08-17T09:00:00Z",
      last_seen_at: "2026-08-17T09:02:00Z",
    },
    {
      chunk_id: "chunk-2",
      verdict: "difficulty_then_recovered",
      focused_seconds: 30,
      difficulty_seconds: 20,
      intervention_count: 1,
      first_seen_at: "2026-08-17T09:02:00Z",
      last_seen_at: "2026-08-17T09:02:50Z",
    },
    {
      chunk_id: "chunk-3",
      verdict: "not_reached",
      focused_seconds: 0,
      difficulty_seconds: 0,
      intervention_count: 0,
      first_seen_at: null,
      last_seen_at: null,
    },
  ],
};

export function fetchMockComplianceReport(sessionId) {
  const report = [
    MOCK_COMPLETE_REPORT,
    MOCK_INSUFFICIENT_DATA_REPORT,
    MOCK_REPORT_WITH_CRITICAL_SECTIONS,
  ].find((candidate) => candidate.session_id === sessionId);
  return Promise.resolve(report ?? null);
}

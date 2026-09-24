/**
 * Calm, non-clinical wording for values that come from Module 8's contracts.
 *
 * The contracts (shared/contracts/) use precise system category names —
 * "struggling", "unknown outcome" — which are the right words for a schema
 * but the wrong words to put in front of a learner. This is the one place
 * those get translated into supportive, judgment-free language, so no
 * component has to invent its own copy for the same underlying value. Per
 * the project's neurodiversity-aware design requirement, engagement
 * difficulty is never framed as failure.
 */

export const ENGAGEMENT_STATE_LABELS = {
  focused: "Focused",
  drifting: "Attention drifting",
  struggling: "Working through a tough spot",
  fatigued: "Needing a rest",
  recovered: "Back on track",
  unknown: "Not measured",
};

export const ENGAGEMENT_STATE_ORDER = [
  "focused",
  "recovered",
  "drifting",
  "struggling",
  "fatigued",
  "unknown",
];

export const INTERVENTION_TYPE_LABELS = {
  simplify_content: "Simplified text",
  bullet_summary: "Quick summary",
  break_suggestion: "Break suggested",
  assistant_help_prompt: "Assistant offered",
  other: "Other support",
};

export const INSIGHT_STATUS_LABELS = {
  pending: "Preparing your summary",
  generated: "AI-written summary",
  fallback_generated: "Summary (simplified version)",
  failed: "Summary unavailable",
};

export const SESSION_STATUS_LABELS = {
  created: "Not started yet",
  active: "In progress",
  paused: "Paused",
  completed: "Completed",
  abandoned: "Ended early",
};

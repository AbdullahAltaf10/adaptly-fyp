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

/**
 * Delivery status for one individual piece of support (Issue #31's
 * intervention log), from shared/contracts/intervention-event.schema.json.
 * "failed" here means the support itself didn't display/complete — it is
 * never used to describe the learner.
 */
export const DELIVERY_STATUS_LABELS = {
  offered: "Offered",
  displayed: "Shown",
  accepted: "Accepted",
  dismissed: "Dismissed",
  completed: "Completed",
  failed: "Didn't load",
};

/**
 * Outcome for one individual piece of support. Calm, non-judgmental
 * phrasing per CLAUDE.md 6.5 — never "failed"/"ineffective" language aimed
 * at the learner.
 */
export const OUTCOME_LABELS = {
  not_observed: "Outcome not observed",
  recovered: "Helped you get back on track",
  improved: "Seemed to help",
  unchanged: "Didn't seem to change things",
  worsened: "Didn't help this time",
  dismissed: "Dismissed before it could help",
  unknown: "Not enough information",
};

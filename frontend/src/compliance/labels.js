/**
 * Calm, non-clinical wording for Module 10's compliance report values.
 *
 * Same rule Module 8's own `src/analytics/labels.js` documents: the
 * contracts use precise system category names, which are the wrong words to
 * put in front of a learner. An excluded score component or a critical
 * section that shows difficulty is normal information, not a verdict on the
 * learner, and the wording here must never read as one.
 */

export const CRITICAL_SECTION_VERDICT_LABELS = {
  sustained_engagement: "Stayed engaged",
  difficulty_then_recovered: "Found it tricky, then got back on track",
  difficulty_not_recovered: "Found it tricky",
  not_reached: "Not reached",
  insufficient_data: "Not enough data",
};

export const SCORE_COMPONENT_LABELS = {
  attentional_presence: "Time spent focused",
  critical_section_engagement: "Engagement with key sections",
  recovery_rate: "Bouncing back after support",
  chatbot_engagement: "Assistant conversations",
};

export const COMPLIANCE_STATUS_LABELS = {
  complete: "Score calculated",
  insufficient_data: "Not enough data for a score yet",
};

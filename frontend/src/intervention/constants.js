/**
 * Module 4 constants shared between the hook and the components.
 *
 * The two lists below are not cosmetic groupings. Module 8 begins measuring
 * whether an intervention helped from a different delivery status depending on
 * which list a type is in:
 *
 *     automatic          displayed | accepted | completed
 *     learner-initiated  accepted | completed
 *
 * So a learner-initiated intervention that is only ever shown contributes
 * nothing to any recovery metric, however long it sits on screen. That is why
 * the break suggestion and the assistant prompt both have an explicit accept
 * action and the simplification does not need one - it is experienced the
 * moment it is rendered.
 */

export const SIMPLIFY_CONTENT = "simplify_content";
export const BULLET_SUMMARY = "bullet_summary";
export const BREAK_SUGGESTION = "break_suggestion";
export const ASSISTANT_HELP_PROMPT = "assistant_help_prompt";

/** Experienced once shown. */
export const AUTOMATIC_TYPES = [SIMPLIFY_CONTENT, BULLET_SUMMARY];

/** Not experienced until the learner acts. */
export const LEARNER_INITIATED_TYPES = [BREAK_SUGGESTION, ASSISTANT_HELP_PROMPT];

/** The two types whose text comes from GET /intervention/{id}/content. */
export const GENERATED_TYPES = AUTOMATIC_TYPES;

export const STATUS_DISPLAYED = "displayed";
export const STATUS_ACCEPTED = "accepted";
export const STATUS_DISMISSED = "dismissed";
export const STATUS_COMPLETED = "completed";
export const STATUS_FAILED = "failed";

export function needsGeneratedText(type) {
  return GENERATED_TYPES.includes(type);
}

/**
 * Mirrors the backend's RECOVERY_ELIGIBLE. Used by the tests to assert that
 * every path a learner can take through the UI reaches a status Module 8
 * measures, rather than trusting that it does.
 */
export function startsRecoveryMeasurement(type, status) {
  if (AUTOMATIC_TYPES.includes(type)) {
    return [STATUS_DISPLAYED, STATUS_ACCEPTED, STATUS_COMPLETED].includes(status);
  }
  if (LEARNER_INITIATED_TYPES.includes(type)) {
    return [STATUS_ACCEPTED, STATUS_COMPLETED].includes(status);
  }
  return false;
}

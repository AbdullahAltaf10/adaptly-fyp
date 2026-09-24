/**
 * Formatting helpers shared by every analytics display component.
 *
 * Every function here follows one rule: a missing value (`null`/`undefined`)
 * always renders as the text "Not available" — never as 0, 0%, or a blank
 * string. Per Module 8's contracts (see CLAUDE.md 6.5), `null` means "this
 * genuinely could not be measured", which is a different fact from a real
 * zero, and showing the two the same way would mislead a learner about
 * their own session.
 */

export const NOT_AVAILABLE = "Not available";

export function formatDurationSeconds(seconds) {
  if (seconds === null || seconds === undefined) return NOT_AVAILABLE;
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes === 0) return `${secs}s`;
  if (secs === 0) return `${minutes}m`;
  return `${minutes}m ${secs}s`;
}

/** For 0-1 fractions (e.g. recovery_rate, effectiveness_rate). */
export function formatFraction(fraction) {
  if (fraction === null || fraction === undefined) return NOT_AVAILABLE;
  return `${Math.round(fraction * 100)}%`;
}

/** For values already on a 0-100 scale (engagement_distribution.percentage). */
export function formatPercentage(percentage) {
  if (percentage === null || percentage === undefined) return NOT_AVAILABLE;
  return `${Math.round(percentage)}%`;
}

export function formatCount(value) {
  if (value === null || value === undefined) return NOT_AVAILABLE;
  return String(value);
}

/**
 * The session's start time, derived from `completed_at` and
 * `duration_seconds` (both required on every session summary) rather than
 * from `timeline_segments[0]` (which can be missing, sparse, or start after
 * a real gap) — this is the one basis `EngagementTimeline` and
 * `InterventionLog` share so a support event lines up with the same point
 * on both. Returns `null` if either input is missing/invalid.
 */
export function computeSessionStartIso(summary) {
  if (!summary?.completed_at || summary?.duration_seconds == null) return null;
  const completedMs = new Date(summary.completed_at).getTime();
  if (Number.isNaN(completedMs)) return null;
  return new Date(completedMs - summary.duration_seconds * 1000).toISOString();
}

export function formatDate(isoString) {
  if (!isoString) return NOT_AVAILABLE;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return NOT_AVAILABLE;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

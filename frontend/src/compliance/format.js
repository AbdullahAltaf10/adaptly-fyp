/**
 * Formatting helpers for Module 10's compliance views.
 *
 * Deliberately a small, separate copy of the same "missing is never zero"
 * rule Module 8's own `src/analytics/format.js` follows, rather than an
 * import from it: Module 10 doesn't take a dependency on Module 8's
 * frontend internals just for two formatting functions, the same way its
 * backend doesn't import Module 8's persistence helpers directly (see
 * `backend/app/compliance/persistence/base.py`).
 */

export const NOT_AVAILABLE = "Not available";

export function formatScore(score) {
  if (score === null || score === undefined) return NOT_AVAILABLE;
  return `${score}/100`;
}

export function formatFraction(fraction) {
  if (fraction === null || fraction === undefined) return NOT_AVAILABLE;
  return `${Math.round(fraction * 100)}%`;
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

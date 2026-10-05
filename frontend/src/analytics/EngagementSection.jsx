import { formatPercentage, NOT_AVAILABLE } from "./format";
import { ENGAGEMENT_STATE_LABELS, ENGAGEMENT_STATE_ORDER } from "./labels";

/**
 * Structural placeholder for the engagement breakdown.
 *
 * This intentionally shows only the simple per-state percentages already
 * available from the session summary — a full second-by-second timeline
 * view is Issue #31's job. Each bar has a plain-text equivalent (the
 * percentage in the row itself, plus one summary sentence) rather than
 * relying on bar length or color alone, per the accessibility requirement
 * that analytics visuals have a text description.
 *
 * Colour is deliberately gentle: `focused`/`recovered` get a small positive
 * accent, and every state that describes difficulty shares one neutral tone
 * rather than a red/orange gradient. The report's own labels already avoid
 * clinical language ("Needing a rest", not "Fatigued") - colour-coding
 * difficulty as alarming would undercut that in the same breath.
 */
const POSITIVE_STATES = new Set(["focused", "recovered"]);

/**
 * Whether any engagement was measured. A session with nothing measured still
 * arrives with a distribution, all of it "unknown"; that is not a result.
 */
export function isEngagementMeasured(distribution) {
  return Boolean(distribution) && !(distribution.unknown?.percentage >= 100);
}

export default function EngagementSection({ distribution }) {
  const hasData = isEngagementMeasured(distribution);
  const focusedPercentage = distribution?.focused?.percentage;

  return (
    <section aria-labelledby="engagement-summary-heading" className="mb-4">
      <h2 id="engagement-summary-heading" className="text-lg font-semibold mb-3">
        Engagement summary
      </h2>

      {!hasData && (
        <p className="text-muted">
          Not enough data was collected to show an engagement breakdown for this session.
        </p>
      )}

      {hasData && (
        <div className="rounded-card border border-line bg-surface shadow-card p-4">
          <p className="mt-0 text-sm text-ink">
            {focusedPercentage === null || focusedPercentage === undefined
              ? "How much of this session was spent focused could not be measured."
              : `You were focused for about ${formatPercentage(focusedPercentage)} of this session.`}
          </p>
          <ul className="list-none p-0 m-0 space-y-2.5">
            {ENGAGEMENT_STATE_ORDER.map((state) => {
              const measure = distribution[state];
              const percentage = measure ? formatPercentage(measure.percentage) : NOT_AVAILABLE;
              const widthPercent =
                measure?.percentage != null ? Math.max(0, Math.min(100, measure.percentage)) : 0;
              return (
                <li key={state}>
                  <div className="flex justify-between text-sm text-ink">
                    <span>{ENGAGEMENT_STATE_LABELS[state]}</span>
                    <span className="text-muted">{percentage}</span>
                  </div>
                  <div
                    role="img"
                    aria-label={`${ENGAGEMENT_STATE_LABELS[state]}: ${percentage}`}
                    className="h-1.5 rounded-full bg-page overflow-hidden mt-1"
                  >
                    <div
                      className={`h-full transition-[width] duration-300 ease-out ${
                        POSITIVE_STATES.has(state) ? "bg-success" : "bg-line-strong"
                      }`}
                      style={{ width: `${widthPercent}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

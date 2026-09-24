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
 */
export default function EngagementSection({ distribution }) {
  const hasData = Boolean(distribution);
  const focusedPercentage = distribution?.focused?.percentage;

  return (
    <section aria-labelledby="engagement-summary-heading">
      <h2 id="engagement-summary-heading">Engagement summary</h2>

      {!hasData && (
        <p>Not enough data was collected to show an engagement breakdown for this session.</p>
      )}

      {hasData && (
        <>
          <p>
            {focusedPercentage === null || focusedPercentage === undefined
              ? "How much of this session was spent focused could not be measured."
              : `You were focused for about ${formatPercentage(focusedPercentage)} of this session.`}
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {ENGAGEMENT_STATE_ORDER.map((state) => {
              const measure = distribution[state];
              const percentage = measure ? formatPercentage(measure.percentage) : NOT_AVAILABLE;
              const widthPercent =
                measure?.percentage != null ? Math.max(0, Math.min(100, measure.percentage)) : 0;
              return (
                <li key={state} style={{ margin: "0.4rem 0" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.9rem" }}>
                    <span>{ENGAGEMENT_STATE_LABELS[state]}</span>
                    <span>{percentage}</span>
                  </div>
                  <div
                    role="img"
                    aria-label={`${ENGAGEMENT_STATE_LABELS[state]}: ${percentage}`}
                    style={{
                      height: "6px",
                      background: "#e8e8e8",
                      borderRadius: "3px",
                      overflow: "hidden",
                      marginTop: "0.2rem",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${widthPercent}%`,
                        background: "#0b6bcb",
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

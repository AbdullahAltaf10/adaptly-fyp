import { formatDurationSeconds, NOT_AVAILABLE } from "./format";
import {
  DELIVERY_STATUS_LABELS,
  ENGAGEMENT_STATE_LABELS,
  INTERVENTION_TYPE_LABELS,
  OUTCOME_LABELS,
} from "./labels";

/**
 * The itemized companion to `InterventionSection`'s totals (Issue #30):
 * where that section says "support was offered 2 times, helped 1," this
 * lists each individual time, in order, with what triggered it and what
 * happened. See the `interventions` note in `mockData.js` — there is no
 * real per-event endpoint yet, so this renders whatever the data source
 * provides and degrades to the empty state if it's missing entirely
 * (e.g. before that endpoint exists).
 *
 * Deliberately distinct empty-state copy from `InterventionSection`'s: the
 * two sit on the same page, and a test regression once caught them
 * colliding on near-identical text when there's nothing to show.
 */
export default function InterventionLog({ interventions, sessionStartIso }) {
  const hasEvents = Array.isArray(interventions) && interventions.length > 0;

  if (!hasEvents) {
    return (
      <section aria-labelledby="intervention-log-heading">
        <h2 id="intervention-log-heading">Support log</h2>
        <p>There&apos;s nothing logged here — no individual support events for this session.</p>
      </section>
    );
  }

  const sessionStartMs = sessionStartIso ? new Date(sessionStartIso).getTime() : null;
  const sorted = [...interventions].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  return (
    <section aria-labelledby="intervention-log-heading">
      <h2 id="intervention-log-heading">Support log</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {sorted.map((event) => {
          const eventMs = new Date(event.timestamp).getTime();
          const elapsedLabel =
            sessionStartMs !== null && !Number.isNaN(eventMs)
              ? formatDurationSeconds(Math.max(0, (eventMs - sessionStartMs) / 1000))
              : NOT_AVAILABLE;
          const typeLabel =
            INTERVENTION_TYPE_LABELS[event.intervention_type] ?? event.intervention_type;
          const stateLabel =
            ENGAGEMENT_STATE_LABELS[event.triggering_engagement_state] ??
            event.triggering_engagement_state;
          const deliveryLabel =
            DELIVERY_STATUS_LABELS[event.delivery_status] ?? event.delivery_status;
          const outcomeLabel = OUTCOME_LABELS[event.outcome] ?? event.outcome;

          return (
            <li
              key={event.intervention_id}
              style={{
                border: "1px solid #ddd",
                borderRadius: "8px",
                padding: "0.75rem 1rem",
                margin: "0 0 0.6rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", color: "#555" }}>
                <span>{elapsedLabel} into the session</span>
                <span>{deliveryLabel}</span>
              </div>
              <p style={{ margin: "0.3rem 0 0", fontWeight: 600 }}>{typeLabel}</p>
              {event.reason && <p style={{ margin: "0.2rem 0 0" }}>{event.reason}</p>}
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.9rem" }}>
                Prompted while: {stateLabel}
              </p>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.9rem" }}>{outcomeLabel}</p>
              {event.recovery_duration_seconds != null && (
                <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "#555" }}>
                  Back on track after {formatDurationSeconds(event.recovery_duration_seconds)}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

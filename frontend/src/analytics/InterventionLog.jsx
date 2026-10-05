import { Clock, Coffee, ListChecks, MessageCircleQuestion, Wand2 } from "lucide-react";

import { formatDurationSeconds, NOT_AVAILABLE } from "./format";
import {
  DELIVERY_STATUS_LABELS,
  ENGAGEMENT_STATE_LABELS,
  INTERVENTION_TYPE_LABELS,
  OUTCOME_LABELS,
} from "./labels";

/** Same four icons InterventionHost uses live, so a learner sees one
    consistent visual vocabulary for "what kind of support was this" whether
    they are looking at it during the session or afterwards in this log. */
const TYPE_ICONS = {
  simplify_content: Wand2,
  bullet_summary: ListChecks,
  break_suggestion: Coffee,
  assistant_help_prompt: MessageCircleQuestion,
};

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
      <section aria-labelledby="intervention-log-heading" className="mb-4">
        <h2 id="intervention-log-heading" className="text-lg font-semibold mb-2">
          Support log
        </h2>
        <p className="text-muted">
          There&apos;s nothing logged here — no individual support events for this session.
        </p>
      </section>
    );
  }

  const sessionStartMs = sessionStartIso ? new Date(sessionStartIso).getTime() : null;
  const sorted = [...interventions].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  return (
    <section aria-labelledby="intervention-log-heading" className="mb-4">
      <h2 id="intervention-log-heading" className="text-lg font-semibold mb-2">
        Support log
      </h2>
      <ul className="list-none p-0 m-0 space-y-2">
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
          const TypeIcon = TYPE_ICONS[event.intervention_type] ?? MessageCircleQuestion;

          return (
            <li
              key={event.intervention_id}
              className="rounded-card border border-line bg-surface shadow-card p-4"
            >
              <div className="flex justify-between text-xs text-muted">
                <span className="flex items-center gap-1">
                  <Clock size={12} strokeWidth={1.75} aria-hidden="true" />
                  {elapsedLabel} into the session
                </span>
                <span>{deliveryLabel}</span>
              </div>
              <p className="flex items-center gap-1.5 mt-1.5 mb-0 font-semibold text-ink">
                <TypeIcon size={15} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                {typeLabel}
              </p>
              {event.reason && <p className="mt-1 mb-0 text-sm text-ink">{event.reason}</p>}
              <p className="mt-1 mb-0 text-sm text-muted">Prompted while: {stateLabel}</p>
              <p className="mt-1 mb-0 text-sm text-ink">{outcomeLabel}</p>
              {event.recovery_duration_seconds != null && (
                <p className="mt-1 mb-0 text-xs text-muted">
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

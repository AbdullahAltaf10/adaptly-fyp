import { formatDurationSeconds, formatFraction, NOT_AVAILABLE } from "./format";
import { INTERVENTION_TYPE_LABELS } from "./labels";

/**
 * Support offered during the session (simplify, summarize, suggest a break,
 * assistant prompt) and whether it seemed to help. Language stays neutral:
 * "didn't help this time" and "not enough information" instead of "failed"
 * or "ineffective", per the neurodiversity-aware design requirement.
 *
 * Scope 6.8 asks for "the average recovery time after each type of response".
 * The key-numbers row above carries one average across the whole session,
 * which answers a different question: a break and a bullet summary are not
 * the same promise, and one number describes neither. `recoveryMetrics.by_type`
 * is what lets each line say how long that particular kind of support took to
 * land. It is optional - summaries computed before it existed do not carry it,
 * and those lines simply say nothing about timing rather than showing a zero.
 */
export default function InterventionSection({ interventionMetrics, recoveryMetrics }) {
  const totalCount = interventionMetrics?.total_count ?? 0;

  if (totalCount === 0) {
    return (
      <section aria-labelledby="intervention-summary-heading">
        <h2 id="intervention-summary-heading">Support offered</h2>
        <p>No extra support was offered during this session — you were on track throughout.</p>
      </section>
    );
  }

  const { effective_count: effectiveCount, ineffective_count: ineffectiveCount, unknown_outcome_count: unknownCount, by_type: byType } =
    interventionMetrics;

  const recoveryByType = new Map(
    (recoveryMetrics?.by_type ?? []).map((item) => [item.intervention_type, item])
  );

  return (
    <section aria-labelledby="intervention-summary-heading">
      <h2 id="intervention-summary-heading">Support offered</h2>
      <p>
        Support was offered {totalCount} time{totalCount === 1 ? "" : "s"}: helped {effectiveCount},
        didn&apos;t help that time {ineffectiveCount}, not enough information {unknownCount}.
      </p>
      <ul>
        {(byType ?? []).map((item) => {
          const recovery = recoveryByType.get(item.intervention_type);
          const averageSeconds = recovery?.average_recovery_time_seconds ?? null;
          return (
            <li key={item.intervention_type}>
              {INTERVENTION_TYPE_LABELS[item.intervention_type] ?? item.intervention_type}
              {" — used "}
              {item.total_count} time{item.total_count === 1 ? "" : "s"}, helped{" "}
              {item.effectiveness_rate === null
                ? NOT_AVAILABLE.toLowerCase()
                : `${formatFraction(item.effectiveness_rate)} of the time`}
              {averageSeconds !== null && (
                <>
                  {", and when it helped you were back on track in about "}
                  {formatDurationSeconds(averageSeconds)}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

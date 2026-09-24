import { formatFraction, NOT_AVAILABLE } from "./format";
import { INTERVENTION_TYPE_LABELS } from "./labels";

/**
 * Support offered during the session (simplify, summarize, suggest a break,
 * assistant prompt) and whether it seemed to help. Language stays neutral:
 * "didn't help this time" and "not enough information" instead of "failed"
 * or "ineffective", per the neurodiversity-aware design requirement.
 */
export default function InterventionSection({ interventionMetrics }) {
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

  return (
    <section aria-labelledby="intervention-summary-heading">
      <h2 id="intervention-summary-heading">Support offered</h2>
      <p>
        Support was offered {totalCount} time{totalCount === 1 ? "" : "s"}: helped {effectiveCount},
        didn&apos;t help that time {ineffectiveCount}, not enough information {unknownCount}.
      </p>
      <ul>
        {(byType ?? []).map((item) => (
          <li key={item.intervention_type}>
            {INTERVENTION_TYPE_LABELS[item.intervention_type] ?? item.intervention_type}
            {" — used "}
            {item.total_count} time{item.total_count === 1 ? "" : "s"}, helped{" "}
            {item.effectiveness_rate === null
              ? NOT_AVAILABLE.toLowerCase()
              : `${formatFraction(item.effectiveness_rate)} of the time`}
          </li>
        ))}
      </ul>
    </section>
  );
}

import { NOT_AVAILABLE } from "./format";

/**
 * One reusable stat tile: a label and an already-formatted value.
 *
 * Formatting (including the "Not available" fallback for missing data)
 * happens in the caller via `src/analytics/format.js`, so this component
 * stays a plain, easily-testable presentational box.
 */
export default function SummaryCard({ label, value, description, icon: Icon }) {
  const isUnavailable = value === NOT_AVAILABLE;

  return (
    <div
      role="group"
      aria-label={label}
      className="rounded-card border border-line bg-surface shadow-card px-4 py-3.5 min-w-[160px]"
    >
      <p className="m-0 flex items-center gap-1.5 text-sm text-muted">
        {Icon && <Icon size={14} strokeWidth={1.75} className="shrink-0 text-accent" aria-hidden="true" />}
        {label}
      </p>
      <p className={`mt-1 mb-0 text-2xl font-semibold ${isUnavailable ? "text-muted" : "text-ink"}`}>
        {value}
      </p>
      {description && <p className="mt-1 mb-0 text-xs text-muted">{description}</p>}
    </div>
  );
}

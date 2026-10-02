import { formatCount, formatDate, formatDurationSeconds, NOT_AVAILABLE } from "./format";
import { SESSION_STATUS_LABELS } from "./labels";

/**
 * The top-of-page summary: what the session was, when, and how it ended.
 */
export default function SessionOverview({ overview, summary }) {
  const contentTitle = overview?.content_title || NOT_AVAILABLE;
  const statusLabel =
    SESSION_STATUS_LABELS[overview?.session_status] ?? NOT_AVAILABLE;

  return (
    <section
      aria-labelledby="session-overview-heading"
      className="rounded-card border border-line bg-surface shadow-card p-4 mb-4"
    >
      <h2 id="session-overview-heading" className="m-0 mb-3 text-lg font-semibold">
        Session overview
      </h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 m-0 text-sm">
        <dt className="text-muted">Content</dt>
        <dd className="m-0 text-ink">{contentTitle}</dd>

        <dt className="text-muted">Date</dt>
        <dd className="m-0 text-ink">{formatDate(summary?.completed_at)}</dd>

        <dt className="text-muted">Duration</dt>
        <dd className="m-0 text-ink">{formatDurationSeconds(summary?.duration_seconds)}</dd>

        <dt className="text-muted">Status</dt>
        <dd className="m-0 text-ink">{statusLabel}</dd>

        <dt className="text-muted">Sections completed</dt>
        <dd className="m-0 text-ink">{formatCount(summary?.chunks_completed)}</dd>
      </dl>
    </section>
  );
}

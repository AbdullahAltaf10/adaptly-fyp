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
    <section aria-labelledby="session-overview-heading">
      <h2 id="session-overview-heading">Session overview</h2>
      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          columnGap: "0.75rem",
          rowGap: "0.4rem",
          margin: 0,
        }}
      >
        <dt style={{ color: "#555" }}>Content</dt>
        <dd style={{ margin: 0 }}>{contentTitle}</dd>

        <dt style={{ color: "#555" }}>Date</dt>
        <dd style={{ margin: 0 }}>{formatDate(summary?.completed_at)}</dd>

        <dt style={{ color: "#555" }}>Duration</dt>
        <dd style={{ margin: 0 }}>{formatDurationSeconds(summary?.duration_seconds)}</dd>

        <dt style={{ color: "#555" }}>Status</dt>
        <dd style={{ margin: 0 }}>{statusLabel}</dd>

        <dt style={{ color: "#555" }}>Sections completed</dt>
        <dd style={{ margin: 0 }}>{formatCount(summary?.chunks_completed)}</dd>
      </dl>
    </section>
  );
}

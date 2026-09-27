import { Link } from "react-router-dom";

import {
  computeSessionStartIso,
  formatDate,
  formatDurationSeconds,
  formatPercentage,
} from "./format";

/**
 * The learner's finished sessions.
 *
 * Scope 6.1 lists session history as part of what a learner's profile stores,
 * and the dashboard mockup shows a "Recent sessions" list. The endpoint
 * (`GET /api/analytics/sessions`) and its client wrapper both existed; nothing
 * ever rendered them, so a learner could only ever see their single most
 * recent session and had no way back to an earlier one.
 *
 * Every item links to the analytics for that session, which is what makes an
 * older session reachable at all.
 */
export default function SessionHistoryList({ items }) {
  const sessions = items ?? [];

  if (sessions.length === 0) {
    return (
      <section aria-labelledby="session-history-heading">
        <h2 id="session-history-heading">Your sessions</h2>
        <p>
          No finished sessions yet. When you finish one, it will appear here with
          what happened during it.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="session-history-heading">
      <h2 id="session-history-heading">Your sessions</h2>
      <ul>
        {sessions.map((summary) => {
          const focused = summary.engagement_distribution?.focused_percentage;
          return (
            <li key={summary.session_id}>
              <Link to={`/analytics?session=${encodeURIComponent(summary.session_id)}`}>
                {formatDate(computeSessionStartIso(summary) ?? summary.completed_at)}
              </Link>
              {" — "}
              {formatDurationSeconds(summary.duration_seconds)}
              {focused !== null && focused !== undefined && (
                <>
                  {", focused "}
                  {formatPercentage(focused)}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

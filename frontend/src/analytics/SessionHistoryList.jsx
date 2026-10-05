import { Clock, FolderOpen, Target } from "lucide-react";
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
        <h2 id="session-history-heading" className="text-lg font-semibold mb-2">
          Your sessions
        </h2>
        <div className="rounded-card border border-line bg-surface shadow-card p-4 flex flex-col items-center text-center py-8">
          <FolderOpen size={32} strokeWidth={1.5} className="text-muted mb-2" aria-hidden="true" />
          <p className="text-muted m-0">
            No finished sessions yet. When you finish one, it will appear here with
            what happened during it.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section aria-labelledby="session-history-heading">
      <h2 id="session-history-heading" className="text-lg font-semibold mb-2">
        Your sessions
      </h2>
      <ul className="list-none p-0 m-0 space-y-2">
        {sessions.map((summary) => {
          const focused = summary.engagement_distribution?.focused_percentage;
          return (
            <li
              key={summary.session_id}
              className="rounded-card border border-line bg-surface shadow-card p-3.5 flex items-center justify-between gap-3 flex-wrap"
            >
              <Link
                to={`/analytics?session=${encodeURIComponent(summary.session_id)}`}
                className="text-accent hover:underline font-medium"
              >
                {formatDate(computeSessionStartIso(summary) ?? summary.completed_at)}
              </Link>
              <span className="flex items-center gap-3 text-sm text-muted">
                <span className="flex items-center gap-1">
                  <Clock size={13} strokeWidth={1.75} aria-hidden="true" />
                  {formatDurationSeconds(summary.duration_seconds)}
                </span>
                {focused !== null && focused !== undefined && (
                  <span className="flex items-center gap-1">
                    <Target size={13} strokeWidth={1.75} aria-hidden="true" />
                    focused {formatPercentage(focused)}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

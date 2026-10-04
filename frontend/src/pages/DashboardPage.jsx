/**
 * The signed-in home screen - what a learner sees at "/" before choosing
 * anything else.
 *
 * Scope's own mockup (section 12) shows this exact page: a welcome line, a
 * "Start a new session" call to action, four stat tiles (sessions this week,
 * average session, best streak, content covered), and a recent-sessions
 * list. "/" used to just redirect straight to the document list - there was
 * no home screen at all, so a returning learner had no sense of their own
 * progress before diving back into a document.
 *
 * Every number here comes from `GET /api/analytics/sessions`
 * (`fetchSessionHistory`), which already existed and nothing rendered -
 * `computeDashboardStats` (see that file for exactly what each stat means
 * and its honest limits) is the only new arithmetic; nothing here invents a
 * metric the backend does not already produce.
 */

import { Calendar, Flame, FolderOpen, Plus, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchSessionHistory } from "../analytics/api";
import { computeDashboardStats, focusTrend, latestSessionSummary } from "../analytics/dashboardStats";
import { formatCount, formatDate, formatDurationSeconds, NOT_AVAILABLE } from "../analytics/format";
import { INTERVENTION_TYPE_LABELS } from "../analytics/labels";
import ErrorState from "../analytics/ErrorState";
import LoadingState from "../analytics/LoadingState";
import SummaryCard from "../analytics/SummaryCard";
import { useAuth } from "../auth/AuthContext";
import { Card } from "../ui";

/** How many recent sessions to fetch: enough for the stat tiles (a week's
    worth plus streak context) and to show a handful in the list below,
    without pulling a learner's entire history onto their home screen. */
const HISTORY_LIMIT = 30;

function interventionCountOf(item) {
  return (item.intervention_metrics?.by_type ?? []).reduce((sum, t) => sum + (t.total_count ?? 0), 0);
}

function RecentSessionRow({ item }) {
  const focused = item.engagement_distribution?.focused?.percentage;
  const interventions = interventionCountOf(item);
  return (
    <li className="flex items-center justify-between gap-3 py-2.5 border-b border-line last:border-b-0">
      <div className="min-w-0">
        <Link
          to={`/analytics?session=${encodeURIComponent(item.session_id)}`}
          className="text-accent hover:underline font-medium"
        >
          {formatDate(item.completed_at)}
        </Link>
        <p className="m-0 text-sm text-muted">
          {formatDurationSeconds(item.duration_seconds)}
          {focused !== null && focused !== undefined && ` · focused ${Math.round(focused)}%`}
          {` · ${interventions} intervention${interventions === 1 ? "" : "s"}`}
        </p>
      </div>
    </li>
  );
}

export default function DashboardPage({ loadHistory = fetchSessionHistory }) {
  const { profile, currentUser } = useAuth();
  const [state, setState] = useState({ status: "loading", items: [], error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", items: [], error: null });
    loadHistory({ limit: HISTORY_LIMIT })
      .then((data) => {
        if (cancelled) return;
        setState({ status: "ready", items: data.items ?? [], error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", items: [], error });
      });
    return () => {
      cancelled = true;
    };
  }, [loadHistory]);

  const name = profile?.display_name || profile?.name || currentUser?.email || "there";
  const stats = computeDashboardStats(state.items);
  const recent = state.items.slice(0, 5);
  const latest = latestSessionSummary(state.items);
  const trend = focusTrend(state.items);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <h1 className="m-0 text-2xl font-semibold">Welcome, {name}</h1>
        <Link
          to="/library"
          className="inline-flex items-center gap-1.5 min-h-10 px-4 py-2 rounded-md border border-accent bg-accent text-on-accent font-medium hover:bg-accent-hover"
        >
          <Plus size={16} strokeWidth={2} aria-hidden="true" />
          Start a new session
        </Link>
      </div>

      {state.status === "loading" && <LoadingState label="Loading your dashboard..." />}
      {state.status === "error" && <ErrorState kind={state.error?.kind} />}

      {state.status === "ready" && (
        <>
          <section aria-labelledby="stats-heading" className="mb-5">
            <h2 id="stats-heading" className="text-lg font-semibold mb-2">
              Your progress
            </h2>
            <div className="flex flex-wrap gap-3">
              <SummaryCard
                icon={Calendar}
                label="Sessions this week"
                value={formatCount(stats.sessionsThisWeek)}
              />
              <SummaryCard
                icon={Timer}
                label="Average session"
                value={
                  stats.averageDurationSeconds === null
                    ? NOT_AVAILABLE
                    : formatDurationSeconds(stats.averageDurationSeconds)
                }
              />
              <SummaryCard
                icon={Flame}
                label="Best streak"
                value={`${formatCount(stats.longestStreakDays)} day${stats.longestStreakDays === 1 ? "" : "s"}`}
              />
              <SummaryCard
                icon={FolderOpen}
                label="Content covered"
                value={formatCount(stats.documentsCovered)}
              />
            </div>
          </section>

          {latest && (
            <section aria-label="Latest session" className="mb-5">
              <Card className="p-4">
                <h2 className="text-lg font-semibold m-0 mb-2">Latest session</h2>
                <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 m-0 text-sm">
                  <div>
                    <dt className="text-muted">Focused</dt>
                    <dd className="m-0 text-ink font-semibold">
                      {latest.focusedPercentage === null ? NOT_AVAILABLE : `${Math.round(latest.focusedPercentage)}%`}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted">Length</dt>
                    <dd className="m-0 text-ink">{formatDurationSeconds(latest.durationSeconds)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Longest focused stretch</dt>
                    <dd className="m-0 text-ink">
                      {latest.longestFocusedSeconds === null ? NOT_AVAILABLE : formatDurationSeconds(latest.longestFocusedSeconds)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted">Interventions</dt>
                    <dd className="m-0 text-ink font-semibold">{latest.interventionTotal}</dd>
                  </div>
                </dl>
                {latest.interventionTotal > 0 && (
                  <ul className="flex flex-wrap gap-2 list-none p-0 m-0 mt-3">
                    {Object.entries(latest.interventionsByType).map(([type, count]) => (
                      <li key={type} className="text-xs rounded-full border border-line px-2.5 py-1 text-ink">
                        {INTERVENTION_TYPE_LABELS[type] ?? type}: {count}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </section>
          )}

          {trend.length > 0 && (
            <section aria-labelledby="trend-heading" className="mb-5">
              <h2 id="trend-heading" className="text-lg font-semibold mb-2">Focus trend</h2>
              <div
                role="img"
                aria-label={`Focus trend across ${trend.length} session${trend.length === 1 ? "" : "s"}, percent focused`}
                className="flex items-end gap-2 h-32 rounded-card border border-line bg-surface p-3"
              >
                {trend.map((point) => (
                  <div key={point.sessionId} className="flex-1 flex flex-col items-center justify-end h-full min-w-0">
                    <div
                      data-focus-bar
                      title={`${Math.round(point.focused)}% focused`}
                      className="w-full rounded-t bg-accent"
                      style={{ height: `${Math.max(2, Math.min(100, point.focused))}%` }}
                    />
                    <span className="text-[10px] text-muted mt-1 truncate w-full text-center">
                      {formatDate(point.completedAt)}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section aria-labelledby="recent-sessions-heading">
            <div className="flex items-center justify-between mb-2">
              <h2 id="recent-sessions-heading" className="text-lg font-semibold m-0">
                Recent sessions
              </h2>
              <Link to="/library" className="text-sm text-accent hover:underline">
                View all documents
              </Link>
            </div>

            <Card>
              {recent.length === 0 ? (
                <p className="text-muted m-0">
                  Nothing here yet.{" "}
                  <Link to="/library/new" className="text-accent hover:underline">
                    Add a document
                  </Link>{" "}
                  to start your first session.
                </p>
              ) : (
                <ul className="list-none p-0 m-0">
                  {recent.map((item) => (
                    <RecentSessionRow key={item.session_id} item={item} />
                  ))}
                </ul>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}

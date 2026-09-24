/**
 * Post-session analytics dashboard shell (Issue #30).
 *
 * Everything below the active-session guard renders from mock data today
 * (`src/analytics/mockData.js`, via `useSessionAnalytics`). Swapping in the
 * real `GET /api/sessions/{session_id}/analytics` endpoint (Issue #29) later
 * only requires changing `useSessionAnalytics`'s default fetcher — nothing
 * in this file or the components it renders needs to change.
 *
 * This dashboard is intentionally not wired into `App.jsx`'s routing. As its
 * own comment says, that file is a thin placeholder Module 1's real frontend
 * migration will replace, not something other pages should build on top of.
 */

import ActiveSessionNotice from "../analytics/ActiveSessionNotice";
import EngagementSection from "../analytics/EngagementSection";
import ErrorState from "../analytics/ErrorState";
import { formatCount, formatDurationSeconds, formatFraction } from "../analytics/format";
import InsightReport from "../analytics/InsightReport";
import InterventionSection from "../analytics/InterventionSection";
import LoadingState from "../analytics/LoadingState";
import SessionOverview from "../analytics/SessionOverview";
import SummaryCard from "../analytics/SummaryCard";
import { useSessionAnalytics } from "../analytics/useSessionAnalytics";

export default function AnalyticsDashboard({ session, fetchAnalytics, onRetryInsightReport }) {
  const isCompleted = session?.status === "completed";

  // Critical guard: only a completed session's analytics are ever fetched or
  // shown. This is not just a display check — `enabled: isCompleted` below
  // means analytics are never even requested for an active/paused/abandoned
  // session, and the early return means none of the metric-bearing
  // components (SessionOverview, the summary cards, EngagementSection,
  // InterventionSection, InsightReport) are reached while that's true, so
  // there's no path where a learner's in-progress engagement stats or
  // behavioral data get displayed as if the session were over.
  const { status, data, error } = useSessionAnalytics({
    sessionId: session?.sessionId,
    enabled: isCompleted,
    ...(fetchAnalytics ? { fetchAnalytics } : {}),
  });

  if (!isCompleted) {
    return (
      <main aria-labelledby="analytics-dashboard-heading">
        <h1 id="analytics-dashboard-heading">Session summary</h1>
        <ActiveSessionNotice />
      </main>
    );
  }

  return (
    <main aria-labelledby="analytics-dashboard-heading">
      <h1 id="analytics-dashboard-heading">Session summary</h1>

      {status === "loading" && <LoadingState />}
      {status === "error" && <ErrorState kind={error?.kind} />}

      {status === "ready" && data && (
        <>
          <SessionOverview overview={data.overview} summary={data.summary} />

          <section aria-labelledby="key-numbers-heading">
            <h2 id="key-numbers-heading">Key numbers</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
              <SummaryCard
                label="Longest focused period"
                value={formatDurationSeconds(
                  data.summary.longest_focused_period?.duration_seconds ?? null
                )}
              />
              <SummaryCard
                label="Average recovery time"
                value={formatDurationSeconds(
                  data.summary.recovery_metrics.average_recovery_time_seconds
                )}
              />
              <SummaryCard
                label="Recovery rate"
                value={formatFraction(data.summary.recovery_metrics.recovery_rate)}
              />
              <SummaryCard
                label="Support offered"
                value={formatCount(data.summary.intervention_metrics.total_count)}
              />
              <SummaryCard
                label="Assistant interactions"
                value={formatCount(data.summary.assistant_usage.total_event_count)}
              />
            </div>
          </section>

          <EngagementSection distribution={data.summary.engagement_distribution} />
          <InterventionSection interventionMetrics={data.summary.intervention_metrics} />
          <InsightReport insightReport={data.insightReport} onRetry={onRetryInsightReport} />
        </>
      )}
    </main>
  );
}

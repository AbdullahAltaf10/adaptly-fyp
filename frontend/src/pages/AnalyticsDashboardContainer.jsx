/**
 * Loads the learner's real most recent completed session and hands it to
 * `AnalyticsDashboard`, replacing the `{ sessionId: "demo-session", status:
 * "completed" }` placeholder `App.jsx` used before this (see PR #86, which
 * wired the dashboard into `App.jsx`/`router.py` but explicitly deferred
 * this real-session-id wiring as follow-up work).
 *
 * Kept as its own component — rather than inlining this fetch into
 * `App.jsx` — for the same reason `App.jsx` stays thin everywhere else: it
 * lets this piece be unit-tested with an injected fetcher the way
 * `AnalyticsDashboard` already is, without needing Firebase auth/App shell
 * setup in the test.
 */

import { useEffect, useState } from "react";

import { fetchMostRecentCompletedSession, fetchSessionAnalytics } from "../analytics/api";
import EmptyAnalyticsState from "../analytics/EmptyAnalyticsState";
import ErrorState from "../analytics/ErrorState";
import LoadingState from "../analytics/LoadingState";
import AnalyticsDashboard from "./AnalyticsDashboard";

export default function AnalyticsDashboardContainer({
  fetchRecentSession = fetchMostRecentCompletedSession,
  fetchAnalytics = fetchSessionAnalytics,
}) {
  const [state, setState] = useState({ status: "loading", session: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", session: null, error: null });

    fetchRecentSession()
      .then((session) => {
        if (cancelled) return;
        setState({
          status: session ? "ready" : "empty",
          session,
          error: null,
        });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", session: null, error });
      });

    return () => {
      cancelled = true;
    };
  }, [fetchRecentSession]);

  if (state.status === "loading" || state.status === "error" || state.status === "empty") {
    return (
      <main aria-labelledby="analytics-dashboard-heading">
        <h1 id="analytics-dashboard-heading">Session summary</h1>
        {state.status === "loading" && <LoadingState />}
        {state.status === "error" && <ErrorState kind={state.error?.kind} />}
        {state.status === "empty" && <EmptyAnalyticsState />}
      </main>
    );
  }

  return (
    <AnalyticsDashboard
      session={{ sessionId: state.session.session_id, status: "completed" }}
      fetchAnalytics={fetchAnalytics}
    />
  );
}

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

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  fetchMostRecentCompletedSession,
  fetchSessionAnalytics,
  requestInsightReport,
} from "../analytics/api";
import EmptyAnalyticsState from "../analytics/EmptyAnalyticsState";
import ErrorState from "../analytics/ErrorState";
import LoadingState from "../analytics/LoadingState";
import AnalyticsDashboard from "./AnalyticsDashboard";

export default function AnalyticsDashboardContainer({
  fetchRecentSession = fetchMostRecentCompletedSession,
  fetchAnalytics = fetchSessionAnalytics,
  requestReport = requestInsightReport,
}) {
  // `?session=` lets the history list link back to an older session. Without
  // it every link would quietly land on the most recent one instead, which is
  // worse than having no links at all.
  const [searchParams] = useSearchParams();
  const requestedSessionId = searchParams.get("session");

  const [state, setState] = useState({ status: "loading", session: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", session: null, error: null });

    if (requestedSessionId) {
      // A session named in the URL needs no lookup: the analytics fetch below
      // is keyed by id, and it is the request that decides whether this
      // learner may see it. Asking for someone else's id fails there, on the
      // server, rather than here.
      setState({
        status: "ready",
        session: { session_id: requestedSessionId },
        error: null,
      });
      return undefined;
    }

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
  }, [fetchRecentSession, requestedSessionId]);

  // What InsightReport calls to have this session's summary written. Kept here
  // because this is the component that knows the session id and how to refetch.
  const sessionId = state.session?.session_id;
  const generateInsightReport = useCallback(async () => {
    let outcome = null;
    try {
      outcome = await requestReport(sessionId);
    } catch {
      // A failed request still leaves whatever report already exists worth
      // showing, so fall through to the refetch rather than losing it.
    }
    const data = await fetchAnalytics(sessionId);
    return {
      insightReport: data.insightReport,
      retried: outcome?.retried,
      message: outcome?.message ?? null,
    };
  }, [requestReport, fetchAnalytics, sessionId]);

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
      generateInsightReport={generateInsightReport}
    />
  );
}

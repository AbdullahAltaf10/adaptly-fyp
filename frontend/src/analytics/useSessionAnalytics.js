import { useEffect, useState } from "react";

import { fetchMockSessionAnalytics } from "./mockData";

/**
 * Resolves one completed session's post-session analytics.
 *
 * This is the single swap point for connecting the real backend later:
 * `fetchAnalytics` defaults to the mock layer (`fetchMockSessionAnalytics`).
 * Once Module 8's real `GET /api/sessions/{session_id}/analytics` endpoint
 * (Issue #29) is wired up, only the default passed here needs to change to
 * something like `(sessionId) => api.get(`/api/sessions/${sessionId}/analytics`).then(r => r.data)` —
 * no component that consumes this hook needs to change, because they only
 * ever see `{ status, data, error }`.
 *
 * `enabled` exists so callers can withhold fetching entirely (e.g. while a
 * session is still active) rather than just hiding the result once it
 * arrives — see the active-session guard in `AnalyticsDashboard.jsx`.
 */
export function useSessionAnalytics({
  sessionId,
  enabled = true,
  fetchAnalytics = fetchMockSessionAnalytics,
}) {
  const [state, setState] = useState({ status: "idle", data: null, error: null });

  useEffect(() => {
    if (!enabled || !sessionId) {
      setState({ status: "idle", data: null, error: null });
      return undefined;
    }

    let cancelled = false;
    setState({ status: "loading", data: null, error: null });

    fetchAnalytics(sessionId)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", data: null, error });
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, enabled, fetchAnalytics]);

  return state;
}

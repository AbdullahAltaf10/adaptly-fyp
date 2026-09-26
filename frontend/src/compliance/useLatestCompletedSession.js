import { useEffect, useState } from "react";

import { getSessionHistory } from "../analytics/api";

/**
 * Resolves the signed-in learner's most recently completed session, so the
 * compliance report page can show real data without a session id being
 * threaded in from elsewhere yet (the same known limitation `App.jsx`
 * documents for both the compliance report view and Module 8's own
 * analytics dashboard).
 *
 * Reuses Module 8's `GET /api/analytics/sessions` session-history endpoint
 * (Issue #29) rather than inventing a Module 10 equivalent: a session only
 * appears there once its analytics summary has been computed, which only
 * happens once Module 8 has finalized it -- so the first item, requested
 * with `limit: 1` and already sorted most-recent-first by the backend, is
 * exactly "the learner's most recent completed session".
 *
 * `status` is one of `"loading" | "ready" | "empty" | "error" | "idle"`.
 * `"empty"` (no sessions yet) is deliberately distinct from `"error"` (the
 * request itself failed) so callers can show a friendly "nothing yet"
 * message instead of an alert.
 */
export function useLatestCompletedSession({ enabled = true, fetchSessions = getSessionHistory } = {}) {
  const [state, setState] = useState({ status: "loading", sessionId: null, error: null });

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", sessionId: null, error: null });
      return undefined;
    }

    let cancelled = false;
    setState({ status: "loading", sessionId: null, error: null });

    fetchSessions({ limit: 1 })
      .then((response) => {
        if (cancelled) return;
        const items = response?.data?.items ?? [];
        if (items.length === 0) {
          setState({ status: "empty", sessionId: null, error: null });
        } else {
          setState({ status: "ready", sessionId: items[0].session_id, error: null });
        }
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", sessionId: null, error });
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, fetchSessions]);

  return state;
}

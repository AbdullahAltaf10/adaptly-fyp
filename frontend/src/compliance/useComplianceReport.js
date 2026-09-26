import { useEffect, useState } from "react";

import { fetchMockComplianceReport } from "./mockData";

/**
 * Resolves one session's compliance report. Same shape and swap-point
 * pattern as Module 8's own `useSessionAnalytics`: `fetchReport` defaults to
 * the mock layer, and swapping in the real
 * `GET /api/sessions/{session_id}/compliance-report` endpoint (Issue #74)
 * later only requires changing the default passed here.
 */
export function useComplianceReport({ sessionId, enabled = true, fetchReport = fetchMockComplianceReport }) {
  const [state, setState] = useState({ status: "idle", data: null, error: null });

  useEffect(() => {
    if (!enabled || !sessionId) {
      setState({ status: "idle", data: null, error: null });
      return undefined;
    }

    let cancelled = false;
    setState({ status: "loading", data: null, error: null });

    fetchReport(sessionId)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", data: null, error });
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, enabled, fetchReport]);

  return state;
}

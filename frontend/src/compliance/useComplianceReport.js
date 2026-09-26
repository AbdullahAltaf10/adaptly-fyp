import { useEffect, useState } from "react";

import { fetchComplianceReport, isMissingReportError } from "./api";

/**
 * Resolves one session's compliance report. Same shape and swap-point
 * pattern as Module 8's own `useSessionAnalytics`: `fetchReport` now
 * defaults to the real `GET /api/sessions/{session_id}/compliance-report`
 * endpoint (Issue #74) instead of the mock layer -- tests still pass their
 * own `fetchReport` (often backed by `./mockData`) to stay isolated from the
 * network.
 *
 * A report that hasn't been generated yet is a distinct `"missing"` status,
 * not `"error"` -- the backend reports this as a documented 409 (see
 * `isMissingReportError`), and callers use it to offer a "Generate report"
 * action instead of just showing failure text.
 *
 * `refetch` re-runs the fetch against the same `sessionId` -- used after a
 * report is generated, so the page doesn't need its own duplicate fetch
 * logic just to pick up the report that was just created.
 */
export function useComplianceReport({ sessionId, enabled = true, fetchReport = fetchComplianceReport }) {
  const [state, setState] = useState({ status: "idle", data: null, error: null });
  const [reloadToken, setReloadToken] = useState(0);

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
        if (cancelled) return;
        if (isMissingReportError(error)) {
          setState({ status: "missing", data: null, error: null });
        } else {
          setState({ status: "error", data: null, error });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reloadToken exists only to trigger a re-run
  }, [sessionId, enabled, fetchReport, reloadToken]);

  return { ...state, refetch: () => setReloadToken((token) => token + 1) };
}

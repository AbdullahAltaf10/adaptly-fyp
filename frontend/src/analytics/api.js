/**
 * Real Module 8 analytics API calls (Issue #29 endpoints), plus the small
 * adapters that reshape backend responses into what the dashboard
 * components already expect (see `mockData.js` for that shape's origin).
 *
 * This is the client-side counterpart to `backend/app/analytics/api/routes.py`
 * and `docs/api/module-8-analytics-api.md` — read those before changing
 * anything here, since the shapes below are meant to track them exactly.
 */

import api from "../api/client";

/**
 * `GET /api/analytics/sessions` — paginated session history for the signed-in
 * learner. Every item is already a completed session's summary (a summary
 * document only ever exists for a session that finished and was finalized),
 * ordered most-recent-first by `completed_at`. No client-side "is it
 * completed" filtering is needed because of that ordering/existence
 * guarantee — see the endpoint's docstring in `routes.py`.
 */
export function fetchSessionHistory({ limit = 20, offset = 0, contentId } = {}) {
  return api
    .get("/api/analytics/sessions", {
      params: {
        limit,
        offset,
        ...(contentId ? { content_id: contentId } : {}),
      },
    })
    .then((response) => response.data)
    .catch((err) => {
      const error = new Error(err.message || "Failed to load session history.");
      // This endpoint never 404s or returns the summary_missing reason code
      // (see docs/api/module-8-analytics-api.md) — any failure here is a
      // generic problem reaching/using the backend.
      error.kind = "server_error";
      throw error;
    });
}

/**
 * The learner's single most recent completed session, or `null` if they
 * haven't completed one yet. Asks the history endpoint for just one item
 * rather than fetching a full page and slicing client-side.
 */
export function fetchMostRecentCompletedSession() {
  return fetchSessionHistory({ limit: 1 }).then(
    (page) => page.items[0] ?? null
  );
}

/**
 * Maps a failed request to the same `.kind` vocabulary
 * `fetchMockSessionAnalytics` uses (`ErrorState.jsx`'s `COPY` keys):
 * `not_found | summary_missing | server_error`. `classifyError` (shared
 * across the app) only distinguishes generic HTTP outcomes, so the one
 * analytics-specific case — the 409 `analytics_summary_missing` reason code
 * documented for this endpoint — is resolved here from the response body.
 */
function classifyAnalyticsError(err) {
  const status = err.response?.status;
  const reasonCode = err.response?.data?.detail?.reason_code;
  if (status === 404) return "not_found";
  if (status === 409 && reasonCode === "analytics_summary_missing") {
    return "summary_missing";
  }
  // Every other outcome (unauthorized, unreachable, generic server error, an
  // unexpected 409) collapses to `ErrorState`'s "server_error" copy, which is
  // already its fallback for any `kind` it doesn't recognize.
  return "server_error";
}

/**
 * The real replacement for `fetchMockSessionAnalytics`, calling
 * `GET /api/sessions/{session_id}/analytics`. Reshapes the backend's
 * response (the summary fields flattened at the top level, plus an
 * `insight_report` envelope field) into the `{ overview, summary,
 * insightReport }` shape `AnalyticsDashboard`/`useSessionAnalytics` already
 * expect from the mock layer, so no rendering component needs to change.
 *
 * The backend has no `content_title` field anywhere in the session-summary
 * contract (see `shared/contracts/session-summary.schema.json`) — it isn't
 * Module 8's data to own. `overview.content_title` is therefore left
 * `undefined` here; `SessionOverview.jsx` already renders "Not available"
 * for a missing title rather than breaking.
 */
export function fetchSessionAnalytics(sessionId) {
  return api
    .get(`/api/sessions/${sessionId}/analytics`)
    .then((response) => {
      const { insight_report: insightReport, ...summary } = response.data;
      return {
        overview: { session_status: "completed" },
        summary,
        insightReport: insightReport ?? { status: "pending", report_text: null },
      };
    })
    .catch((err) => {
      const error = new Error(
        err.response?.data?.detail?.message || err.message || "Failed to load session analytics."
      );
      error.kind = classifyAnalyticsError(err);
      throw error;
    });
}

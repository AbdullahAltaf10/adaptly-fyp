/**
 * Module 8's session-history endpoint.
 *
 * Wrapped here the same way every other module's `api.js` wraps its own
 * endpoints (see `frontend/src/compliance/api.js`, `frontend/src/engagement/api.js`).
 * Used today by `frontend/src/compliance/useLatestCompletedSession.js` to find
 * a learner's most recently completed session for the compliance report page
 * -- Module 8's own dashboard (`AnalyticsDashboard.jsx`) still takes its
 * session as a prop rather than discovering one itself (see that file's
 * docstring), but the underlying `GET /api/analytics/sessions` endpoint
 * (Issue #29) already exists and behaves like every other real endpoint.
 */

import api from "../api/client";

/** Paginated session history for the signed-in learner, most recent first. */
export function getSessionHistory({ limit, offset, contentId } = {}) {
  return api.get("/api/analytics/sessions", {
    params: {
      ...(limit != null ? { limit } : {}),
      ...(offset != null ? { offset } : {}),
      ...(contentId ? { content_id: contentId } : {}),
    },
  });
}

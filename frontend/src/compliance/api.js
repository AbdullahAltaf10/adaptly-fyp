/**
 * The three Module 10 compliance-report endpoints.
 *
 * Wrapped here the same way `frontend/src/engagement/api.js` and
 * `frontend/src/intervention/api.js` wrap their own modules' endpoints,
 * importing the one shared client rather than each module building its own
 * fetch logic.
 */

import api from "../api/client";

/** Generate (or fetch the existing, unchanged) report for a session. */
export function generateComplianceReport(sessionId) {
  return api.post(`/api/sessions/${sessionId}/compliance-report`);
}

/** Fetch a session's report. Owner or hr_admin only (enforced server-side). */
export function getComplianceReport(sessionId) {
  return api.get(`/api/sessions/${sessionId}/compliance-report`);
}

/** List reports. hr_admin only (enforced server-side). */
export function listComplianceReports({ userId, contentId } = {}) {
  return api.get("/api/compliance/reports", {
    params: {
      ...(userId ? { user_id: userId } : {}),
      ...(contentId ? { content_id: contentId } : {}),
    },
  });
}

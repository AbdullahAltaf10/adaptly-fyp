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

/**
 * `getComplianceReport`, unwrapped to just the report body -- the shape
 * `useComplianceReport`'s `fetchReport` contract expects (mirrors its mock
 * default, `fetchMockComplianceReport`, which also resolves directly to a
 * report rather than an axios response).
 */
export function fetchComplianceReport(sessionId) {
  return getComplianceReport(sessionId).then((response) => response.data);
}

/**
 * True when a failed `GET .../compliance-report` failed specifically because
 * no report has been generated yet (the backend's documented 409 shape, see
 * `backend/app/compliance/api/routes.py::get_compliance_report`), as opposed
 * to a real error. Lets callers offer a "Generate report" action instead of
 * just an error message.
 */
export function isMissingReportError(err) {
  return (
    err?.response?.status === 409 &&
    err?.response?.data?.detail?.reason_code === "compliance_report_missing"
  );
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

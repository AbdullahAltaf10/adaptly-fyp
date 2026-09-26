/**
 * An employee's own compliance report (Issue #75), reachable from Module
 * 8's post-session dashboard.
 *
 * Not wired into `App.jsx`'s routing, on purpose -- Module 8's own
 * `AnalyticsDashboard.jsx` isn't either (see its docstring: `App.jsx` is a
 * documented placeholder pending Module 1's real frontend migration). This
 * page follows the exact same convention rather than inventing new app-wide
 * routing infrastructure that doesn't exist yet.
 */

import ComplianceReportView from "../compliance/ComplianceReportView";
import { useComplianceReport } from "../compliance/useComplianceReport";

export default function ComplianceReportPage({ sessionId, fetchReport }) {
  const { status, data, error } = useComplianceReport({
    sessionId,
    ...(fetchReport ? { fetchReport } : {}),
  });

  return (
    <main aria-labelledby="compliance-report-page-heading">
      <h1 id="compliance-report-page-heading">Compliance report</h1>

      {status === "loading" && <p role="status">Loading your compliance report…</p>}
      {status === "error" && (
        <p role="alert">
          Could not load this report{error?.message ? `: ${error.message}` : "."}
        </p>
      )}
      {status === "ready" && <ComplianceReportView report={data} />}
    </main>
  );
}

/**
 * Minimal hr_admin-only list + detail view for compliance reports
 * (Issue #75). The full HR completion-tracking dashboard is Module 9's job
 * (manual assignment, completion tracking, etc.) -- this is only enough to
 * let an hr_admin actually see the attestation reports Module 10 produces.
 *
 * Like `ComplianceReportPage`, this is not wired into `App.jsx`'s routing --
 * see that file's comment for why.
 */

import { useEffect, useState } from "react";

import ComplianceReportView from "../compliance/ComplianceReportView";
import { listComplianceReports } from "../compliance/api";
import { formatDate, formatScore } from "../compliance/format";

export default function HrComplianceReportsPage({ fetchReports = listComplianceReports }) {
  const [reports, setReports] = useState(null);
  const [error, setError] = useState(null);
  const [selectedSessionId, setSelectedSessionId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchReports()
      .then((response) => {
        if (!cancelled) setReports(response.data?.items ?? response.items ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchReports]);

  const selectedReport = reports?.find((report) => report.session_id === selectedSessionId);

  return (
    <main aria-labelledby="hr-compliance-reports-heading">
      <h1 id="hr-compliance-reports-heading">Compliance reports</h1>

      {error && <p role="alert">Could not load compliance reports.</p>}
      {reports === null && !error && <p role="status">Loading reports…</p>}
      {reports?.length === 0 && <p>No compliance reports have been generated yet.</p>}

      {reports && reports.length > 0 && (
        <table>
          <caption className="sr-only">All compliance reports</caption>
          <thead>
            <tr>
              <th scope="col">Session</th>
              <th scope="col">Learner</th>
              <th scope="col">Generated</th>
              <th scope="col">Score</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.session_id}>
                <td>{report.session_id}</td>
                <td>{report.user_id}</td>
                <td>{formatDate(report.generated_at)}</td>
                <td>{formatScore(report.engagement_quality_score)}</td>
                <td>
                  <button type="button" onClick={() => setSelectedSessionId(report.session_id)}>
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedReport && <ComplianceReportView report={selectedReport} />}
    </main>
  );
}

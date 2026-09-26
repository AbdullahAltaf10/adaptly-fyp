/**
 * An employee's own compliance report (Issue #75), reachable from the app's
 * nav (see `App.jsx`, reconciled with Module 8's own dashboard toggle when
 * both landed in `develop` -- Issue #81).
 *
 * When no `sessionId` is given, this page discovers the learner's most
 * recently completed session itself (`useLatestCompletedSession`, built on
 * Module 8's `GET /api/analytics/sessions`) rather than requiring one to be
 * threaded in from `StudySession` -- that end-to-end wiring is still
 * separate, larger work (see `App.jsx`'s placeholder-session-id note). A
 * learner with no completed sessions yet sees a friendly empty state instead
 * of an error, and a completed session with no report yet gets an explicit
 * "Generate report" action rather than a dead end.
 */

import { useState } from "react";

import { generateComplianceReport } from "../compliance/api";
import ComplianceReportView from "../compliance/ComplianceReportView";
import { useComplianceReport } from "../compliance/useComplianceReport";
import { useLatestCompletedSession } from "../compliance/useLatestCompletedSession";

export default function ComplianceReportPage({ sessionId: sessionIdProp, fetchReport, fetchSessions }) {
  const autoDiscover = sessionIdProp == null;
  const latestSession = useLatestCompletedSession({
    enabled: autoDiscover,
    ...(fetchSessions ? { fetchSessions } : {}),
  });
  const sessionId = autoDiscover ? latestSession.sessionId : sessionIdProp;

  const { status, data, error, refetch } = useComplianceReport({
    sessionId,
    enabled: autoDiscover ? latestSession.status === "ready" : true,
    ...(fetchReport ? { fetchReport } : {}),
  });

  const [generateState, setGenerateState] = useState({ status: "idle", error: null });

  const handleGenerate = async () => {
    setGenerateState({ status: "generating", error: null });
    try {
      await generateComplianceReport(sessionId);
      setGenerateState({ status: "idle", error: null });
      refetch();
    } catch (err) {
      setGenerateState({ status: "idle", error: err });
    }
  };

  if (autoDiscover && latestSession.status === "loading") {
    return (
      <main aria-labelledby="compliance-report-page-heading">
        <h1 id="compliance-report-page-heading">Compliance report</h1>
        <p role="status">Looking for your most recent session…</p>
      </main>
    );
  }

  if (autoDiscover && latestSession.status === "empty") {
    return (
      <main aria-labelledby="compliance-report-page-heading">
        <h1 id="compliance-report-page-heading">Compliance report</h1>
        <p role="status">
          You haven&apos;t completed a study session yet. Finish a session to see your
          compliance report here.
        </p>
      </main>
    );
  }

  if (autoDiscover && latestSession.status === "error") {
    return (
      <main aria-labelledby="compliance-report-page-heading">
        <h1 id="compliance-report-page-heading">Compliance report</h1>
        <p role="alert">
          Could not check for a recent session
          {latestSession.error?.message ? `: ${latestSession.error.message}` : "."}
        </p>
      </main>
    );
  }

  return (
    <main aria-labelledby="compliance-report-page-heading">
      <h1 id="compliance-report-page-heading">Compliance report</h1>

      {status === "loading" && <p role="status">Loading your compliance report…</p>}

      {status === "missing" && (
        <div>
          <p role="status">No compliance report has been generated for this session yet.</p>
          <button onClick={handleGenerate} disabled={generateState.status === "generating"}>
            {generateState.status === "generating" ? "Generating…" : "Generate report"}
          </button>
          {generateState.error && (
            <p role="alert">
              Could not generate the report
              {generateState.error?.message ? `: ${generateState.error.message}` : "."}
            </p>
          )}
        </div>
      )}

      {status === "error" && (
        <p role="alert">
          Could not load this report{error?.message ? `: ${error.message}` : "."}
        </p>
      )}

      {status === "ready" && <ComplianceReportView report={data} />}
    </main>
  );
}

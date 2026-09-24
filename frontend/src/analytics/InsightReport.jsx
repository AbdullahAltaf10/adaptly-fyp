import { INSIGHT_STATUS_LABELS } from "./labels";

/**
 * The AI-written (or deterministic-fallback) session summary.
 *
 * Real Gemini generation is Issue #32's scope — this component only renders
 * whichever status the data is in (`pending | generated | fallback_generated
 * | failed`, matching shared/contracts/analytics-report.schema.json) and
 * offers a retry affordance on failure. It never implies analytics failed
 * just because the written summary did — the numeric sections above this
 * one are unaffected and say so.
 */
export default function InsightReport({ insightReport, onRetry }) {
  if (!insightReport) {
    return (
      <section aria-labelledby="insight-report-heading">
        <h2 id="insight-report-heading">Session summary</h2>
        <p>Not available.</p>
      </section>
    );
  }

  const { status, report_text: reportText } = insightReport;

  return (
    <section aria-labelledby="insight-report-heading">
      <h2 id="insight-report-heading">Session summary</h2>

      {status === "pending" && (
        <p role="status">We&apos;re preparing a written summary of this session.</p>
      )}

      {(status === "generated" || status === "fallback_generated") && (
        <>
          <p style={{ fontSize: "0.8rem", color: "#666", margin: "0 0 0.25rem" }}>
            {INSIGHT_STATUS_LABELS[status]}
          </p>
          <p>{reportText}</p>
        </>
      )}

      {status === "failed" && (
        <div role="status">
          <p>
            We couldn&apos;t prepare a written summary this time. Your session numbers
            above are complete and unaffected.
          </p>
          <button type="button" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </section>
  );
}

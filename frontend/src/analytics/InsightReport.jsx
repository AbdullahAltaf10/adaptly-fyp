import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { INSIGHT_STATUS_LABELS } from "./labels";
import { Button } from "../ui";

/**
 * The AI-written (or deterministic-fallback) session summary.
 *
 * Renders whichever status the data is in (`pending | generated |
 * fallback_generated | failed`, matching shared/contracts/analytics-report.schema.json)
 * and offers a retry affordance on failure. It never implies analytics failed
 * just because the written summary did - the numeric sections above this one
 * are unaffected and say so.
 *
 * **Generation.** Scope 6.8 promises "a personalized insight report ... after
 * every session", but the backend only writes one when
 * `POST .../insight-report/retry` is called, and until now nothing on the
 * frontend ever called it. A session's report therefore stayed `pending`
 * forever while this screen said "We're preparing a written summary" - a
 * sentence with nobody behind it.
 *
 * `generate` is that caller. When it is supplied and the report is `pending`,
 * it is invoked once per session, on first view, rather than at session end:
 * a Gemini call at session end would slow every session finishing and spend the
 * free tier's 20 requests a day on reports nobody opens. It resolves to
 * `{ insightReport, retried, message }`.
 *
 * Without `generate` this component behaves exactly as before, so nothing that
 * already renders it changes.
 */
export default function InsightReport({ insightReport, onRetry, generate, sessionId }) {
  const [override, setOverride] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState(null);
  const attemptedFor = useRef(null);
  const [attempted, setAttempted] = useState(null);

  const current = override ?? insightReport;
  const status = current?.status;

  const run = async () => {
    if (!generate) {
      onRetry?.();
      return;
    }
    setGenerating(true);
    setNotice(null);
    try {
      const result = await generate();
      if (result?.insightReport) setOverride(result.insightReport);
      // The server says why when it declines to try again (no key configured, or
      // the retry budget is spent). Showing that beats a button that appears to
      // do nothing.
      if (result?.retried === false && result?.message) setNotice(result.message);
    } catch {
      setNotice("We could not reach the server to write your summary. Try again in a moment.");
    } finally {
      setGenerating(false);
    }
  };

  // First view of a pending report: write it once.
  useEffect(() => {
    if (!generate || !sessionId) return;
    if (insightReport?.status !== "pending") return;
    if (attemptedFor.current === sessionId) return;
    attemptedFor.current = sessionId;
    setAttempted(sessionId);
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generate, sessionId, insightReport?.status]);

  if (!current) {
    return (
      <section aria-labelledby="insight-report-heading" className="mb-4">
        <h2 id="insight-report-heading" className="text-lg font-semibold mb-2">
          Session summary
        </h2>
        <p className="text-muted">Not available.</p>
      </section>
    );
  }

  const reportText = current.report_text;
  // Until the first attempt has started, a pending report is about to be
  // written, not unavailable - do not flash the wrong sentence for a frame.
  const busy =
    generating || (Boolean(generate && sessionId) && status === "pending" && attempted !== sessionId);

  return (
    <section aria-labelledby="insight-report-heading" className="mb-4">
      <h2 id="insight-report-heading" className="flex items-center gap-1.5 text-lg font-semibold mb-2">
        <Sparkles size={16} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
        Session summary
      </h2>

      <div className="rounded-card border border-line bg-surface shadow-card p-4">
        {busy && (
          <p role="status" className="flex items-center gap-2 text-muted m-0">
            <Loader2 size={14} strokeWidth={1.75} className="animate-spin shrink-0" aria-hidden="true" />
            Writing your summary - this can take a few seconds.
          </p>
        )}

        {!busy && status === "pending" && (
          <p role="status" className="text-ink m-0">
            {generate
              ? "A written summary is not available for this session right now. Your session numbers above are complete."
              : "We're preparing a written summary of this session."}
          </p>
        )}

        {!busy && (status === "generated" || status === "fallback_generated") && (
          <>
            <p className="text-xs text-muted m-0 mb-1">{INSIGHT_STATUS_LABELS[status]}</p>
            <p className="text-ink m-0 leading-relaxed">{reportText}</p>
            {status === "fallback_generated" && generate && (
              <Button variant="quiet" onClick={run} className="mt-2 px-0">
                Try for a fuller written summary
              </Button>
            )}
          </>
        )}

        {!busy && status === "failed" && (
          <div role="status">
            <p className="text-ink m-0 mb-2">
              We couldn&apos;t prepare a written summary this time. Your session numbers
              above are complete and unaffected.
            </p>
            <Button variant="secondary" onClick={run}>
              <RefreshCw size={14} strokeWidth={1.75} aria-hidden="true" />
              Try again
            </Button>
          </div>
        )}

        {notice && (
          <p role="status" className="mt-2 text-sm text-muted">
            {notice}
          </p>
        )}
      </div>
    </section>
  );
}

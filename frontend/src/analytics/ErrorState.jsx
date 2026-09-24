/**
 * Calm, actionable copy for the error cases this dashboard can hit.
 *
 * `kind` matches the `.kind` field `fetchMockSessionAnalytics` (and, later,
 * the real API's `classifyError`) puts on a rejected fetch. `role="alert"`
 * because — unlike loading — an error is unexpected and worth interrupting
 * screen-reader flow for.
 */
const COPY = {
  not_found: {
    heading: "Session not found",
    body: "We couldn't find this session. It may have been removed, or the link may be incorrect.",
  },
  summary_missing: {
    heading: "Summary still processing",
    body: "This session finished, but its summary hasn't finished processing yet. Please check back in a moment.",
  },
  server_error: {
    heading: "Something went wrong",
    body: "We couldn't load this session's summary right now. Please try again.",
  },
};

export default function ErrorState({ kind }) {
  const copy = COPY[kind] ?? COPY.server_error;

  return (
    <div role="alert">
      <h2>{copy.heading}</h2>
      <p>{copy.body}</p>
    </div>
  );
}

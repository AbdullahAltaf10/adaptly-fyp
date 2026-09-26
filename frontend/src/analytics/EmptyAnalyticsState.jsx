/**
 * Shown instead of a summary when the learner hasn't completed a session
 * yet. Distinct from `ErrorState` (something went wrong) and
 * `ActiveSessionNotice` (a specific session is still in progress) — this is
 * the "there's nothing here yet" case for the dashboard as a whole, so it
 * gets its own calm, non-clinical copy rather than reusing either. No chart
 * or number placeholders are rendered alongside it.
 */
export default function EmptyAnalyticsState() {
  return (
    <div role="status">
      <h2>No session summary yet</h2>
      <p>
        Finish a study session and your summary will show up here, with a
        look back at how it went.
      </p>
    </div>
  );
}

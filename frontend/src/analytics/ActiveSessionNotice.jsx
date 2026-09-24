/**
 * Shown instead of analytics whenever the session is not completed.
 *
 * This is the visible half of the active-session guard in
 * `AnalyticsDashboard.jsx` — see that file for why the guard exists and how
 * it's enforced. `role="status"` (not `role="alert"`) because this is the
 * normal, expected state for a session in progress, not a problem.
 */
export default function ActiveSessionNotice() {
  return (
    <div role="status">
      <h2>This session is still in progress</h2>
      <p>Your summary will be ready once you finish studying.</p>
    </div>
  );
}

/**
 * Loading placeholder for the dashboard.
 *
 * Deliberately no spinner or pulsing animation — the issue calls for a
 * clear, calm loading state, and a moving element is exactly the kind of
 * distraction the rest of this dashboard is designed to avoid.
 * `role="status"` + `aria-live="polite"` announce it to screen readers
 * without interrupting anything.
 */
export default function LoadingState() {
  return (
    <div role="status" aria-live="polite">
      <p>Loading your session summary...</p>
    </div>
  );
}

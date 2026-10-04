import { formatDurationSeconds, NOT_AVAILABLE } from "./format";
import { ENGAGEMENT_STATE_LABELS } from "./labels";

/**
 * A fuller, chronological view of the session (Issue #31), sitting alongside
 * `EngagementSection`'s simple percentage breakdown (Issue #30). Renders
 * `timeline_segments` from shared/contracts/session-summary.schema.json in
 * order, left to right across the session's duration, with any support
 * offered (see the `interventions` note in `mockData.js`) marked at the
 * point it happened.
 *
 * `timeline_segments` is not guaranteed to cover every second of the
 * session contiguously — the metric engine only ever emits a segment when
 * it has something to say, so a stretch of time between two segments (or
 * before the first / after the last) is a genuine gap, not "focused by
 * default." Per CLAUDE.md 6.5 ("unknown is not zero"), any such gap is
 * rendered here as its own "Not measured" block rather than silently
 * stretching a neighboring segment or being dropped from the timeline.
 */

// Reuses the app's own theme tokens where a state maps naturally onto one
// (focused/recovered/drifting/unknown), rather than inventing a second,
// unrelated palette just for this chart. `struggling` deliberately does NOT
// get the alarm-adjacent hue a first instinct reaches for - `--color-danger`
// was itself already softened to a muted clay for the same reason
// (see index.css's design principles), so reusing it here keeps this chart
// visually consistent with the calm-by-design rest of the app rather than
// becoming the one place a "bad" state reads as a red flag. `fatigued` is the
// only genuinely new hue, picked to sit in the same muted family as the rest.
const STATE_COLORS = {
  focused: "var(--color-accent)",
  recovered: "var(--color-success)",
  drifting: "var(--color-warning)",
  struggling: "var(--color-danger)",
  fatigued: "#8a5a9e",
  unknown: "var(--color-line-strong)",
};

const MIN_GAP_SECONDS = 1;

function toMs(isoString) {
  const value = new Date(isoString).getTime();
  return Number.isNaN(value) ? null : value;
}

/**
 * Turns the raw (possibly non-contiguous) segment list into a fully
 * time-ordered, gap-filled list, each entry carrying its offset in seconds
 * from the start of the session so callers can position it on a timeline.
 * Synthetic gap entries are marked `synthetic: true` and always use the
 * "unknown" state — they represent time nothing was measured for, not a
 * real observed segment.
 */
function buildTimeline(segments, totalDurationSeconds, sessionStartIso) {
  const usable = (segments ?? [])
    .map((segment) => {
      const startMs = toMs(segment.started_at);
      const endMs = toMs(segment.ended_at);
      if (startMs === null || endMs === null || endMs < startMs) return null;
      return { ...segment, startMs, endMs };
    })
    .filter(Boolean)
    .sort((a, b) => a.startMs - b.startMs);

  if (usable.length === 0) return { entries: [], sessionStartMs: null };

  // Prefer the shared session-start basis (see `computeSessionStartIso` in
  // format.js) so this lines up with `InterventionLog`; fall back to the
  // first segment's own start only if that basis isn't available.
  const sharedStartMs = sessionStartIso ? toMs(sessionStartIso) : null;
  const sessionStartMs = sharedStartMs ?? usable[0].startMs;
  const entries = [];
  let cursorMs = sessionStartMs;

  for (const segment of usable) {
    const gapSeconds = (segment.startMs - cursorMs) / 1000;
    if (gapSeconds >= MIN_GAP_SECONDS) {
      entries.push({
        synthetic: true,
        state: "unknown",
        offsetSeconds: (cursorMs - sessionStartMs) / 1000,
        durationSeconds: gapSeconds,
      });
    }
    entries.push({
      synthetic: false,
      state: segment.state,
      offsetSeconds: (segment.startMs - sessionStartMs) / 1000,
      durationSeconds: (segment.endMs - segment.startMs) / 1000,
      averageConfidence: segment.average_confidence ?? null,
    });
    cursorMs = Math.max(cursorMs, segment.endMs);
  }

  if (totalDurationSeconds !== null && totalDurationSeconds !== undefined) {
    const sessionEndMs = sessionStartMs + totalDurationSeconds * 1000;
    const trailingGapSeconds = (sessionEndMs - cursorMs) / 1000;
    if (trailingGapSeconds >= MIN_GAP_SECONDS) {
      entries.push({
        synthetic: true,
        state: "unknown",
        offsetSeconds: (cursorMs - sessionStartMs) / 1000,
        durationSeconds: trailingGapSeconds,
      });
    }
  }

  return { entries, sessionStartMs };
}

function timeLabel(offsetSeconds) {
  return formatDurationSeconds(Math.max(0, offsetSeconds));
}

export default function EngagementTimeline({
  segments,
  interventions,
  totalDurationSeconds,
  sessionStartIso,
}) {
  const { entries, sessionStartMs } = buildTimeline(
    segments,
    totalDurationSeconds,
    sessionStartIso
  );
  // A timeline made only of "unknown" segments measured nothing: showing it
  // as a full grey block reads as a result, so it gets the empty-state copy.
  const measuredSegments = (segments ?? []).filter((segment) => segment.state && segment.state !== "unknown");
  const hasData = measuredSegments.length > 0 && entries.length > 0 && Boolean(totalDurationSeconds);

  return (
    <section aria-labelledby="engagement-timeline-heading" className="mb-4">
      <h2 id="engagement-timeline-heading" className="text-lg font-semibold mb-2">
        Session timeline
      </h2>

      {!hasData && (
        <p className="text-muted">Not enough data was collected to show a timeline for this session.</p>
      )}

      {hasData && (
        <div className="rounded-card border border-line bg-surface shadow-card p-4">
          <div className="relative flex h-7 rounded-md overflow-hidden border border-line">
            {entries.map((entry, index) => {
              const widthPercent = Math.max(
                0,
                Math.min(100, (entry.durationSeconds / totalDurationSeconds) * 100)
              );
              const label = entry.synthetic
                ? "Not measured"
                : ENGAGEMENT_STATE_LABELS[entry.state] ?? entry.state;
              return (
                <div
                  key={`${entry.state}-${entry.offsetSeconds}-${index}`}
                  role="img"
                  aria-label={`${label}, ${timeLabel(entry.offsetSeconds)} to ${timeLabel(
                    entry.offsetSeconds + entry.durationSeconds
                  )} (${formatDurationSeconds(entry.durationSeconds)})`}
                  style={{
                    width: `${widthPercent}%`,
                    minWidth: widthPercent > 0 ? "2px" : 0,
                    background: STATE_COLORS[entry.state] ?? STATE_COLORS.unknown,
                    opacity: entry.synthetic ? 0.5 : 1,
                  }}
                />
              );
            })}

            {(interventions ?? []).map((event) => {
              const eventMs = toMs(event.timestamp);
              if (eventMs === null || sessionStartMs === null) return null;
              const offsetSeconds = (eventMs - sessionStartMs) / 1000;
              const leftPercent = Math.max(
                0,
                Math.min(100, (offsetSeconds / totalDurationSeconds) * 100)
              );
              return (
                <div
                  key={event.intervention_id}
                  role="img"
                  aria-label={`Support offered at ${timeLabel(offsetSeconds)}`}
                  title={`Support offered at ${timeLabel(offsetSeconds)}`}
                  className="absolute w-0 h-0 -translate-x-1/2"
                  style={{
                    left: `${leftPercent}%`,
                    top: "-4px",
                    borderLeft: "5px solid transparent",
                    borderRight: "5px solid transparent",
                    borderTop: "7px solid var(--color-ink)",
                  }}
                />
              );
            })}
          </div>

          <ol className="list-none p-0 m-0 mt-3 space-y-1 text-sm text-ink">
            {entries.map((entry, index) => {
              const label = entry.synthetic
                ? ENGAGEMENT_STATE_LABELS.unknown ?? NOT_AVAILABLE
                : ENGAGEMENT_STATE_LABELS[entry.state] ?? entry.state;
              const supportDuring = (interventions ?? []).filter((event) => {
                const eventMs = toMs(event.timestamp);
                if (eventMs === null || sessionStartMs === null) return false;
                const eventOffset = (eventMs - sessionStartMs) / 1000;
                return (
                  eventOffset >= entry.offsetSeconds &&
                  eventOffset < entry.offsetSeconds + entry.durationSeconds
                );
              });
              return (
                <li key={`${entry.state}-${entry.offsetSeconds}-${index}`}>
                  {timeLabel(entry.offsetSeconds)}–
                  {timeLabel(entry.offsetSeconds + entry.durationSeconds)}: {label} (
                  {formatDurationSeconds(entry.durationSeconds)})
                  {supportDuring.length > 0 && (
                    <span className="text-muted"> — support offered during this stretch</span>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </section>
  );
}

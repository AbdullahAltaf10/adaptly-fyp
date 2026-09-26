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
 * default." Per PROJECT_CONTEXT.md 6.5 ("unknown is not zero"), any such gap is
 * rendered here as its own "Not measured" block rather than silently
 * stretching a neighboring segment or being dropped from the timeline.
 */

const STATE_COLORS = {
  focused: "#0b6bcb",
  recovered: "#2f9e5b",
  drifting: "#e0a72e",
  struggling: "#d9743c",
  fatigued: "#b25b9e",
  unknown: "#c9c9c9",
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
  const hasData = entries.length > 0 && Boolean(totalDurationSeconds);

  return (
    <section aria-labelledby="engagement-timeline-heading">
      <h2 id="engagement-timeline-heading">Session timeline</h2>

      {!hasData && (
        <p>Not enough data was collected to show a timeline for this session.</p>
      )}

      {hasData && (
        <>
          <div
            style={{
              position: "relative",
              display: "flex",
              height: "28px",
              borderRadius: "6px",
              overflow: "hidden",
              border: "1px solid #ddd",
            }}
          >
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
                  style={{
                    position: "absolute",
                    left: `${leftPercent}%`,
                    top: "-4px",
                    transform: "translateX(-50%)",
                    width: 0,
                    height: 0,
                    borderLeft: "5px solid transparent",
                    borderRight: "5px solid transparent",
                    borderTop: "7px solid #1a1a1a",
                  }}
                />
              );
            })}
          </div>

          <ol style={{ listStyle: "none", padding: 0, margin: "0.75rem 0 0" }}>
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
                <li key={`${entry.state}-${entry.offsetSeconds}-${index}`} style={{ margin: "0.25rem 0", fontSize: "0.9rem" }}>
                  {timeLabel(entry.offsetSeconds)}–
                  {timeLabel(entry.offsetSeconds + entry.durationSeconds)}: {label} (
                  {formatDurationSeconds(entry.durationSeconds)})
                  {supportDuring.length > 0 && " — support offered during this stretch"}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </section>
  );
}

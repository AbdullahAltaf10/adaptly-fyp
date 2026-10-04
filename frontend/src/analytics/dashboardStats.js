/**
 * The home dashboard's four stat tiles, computed from session history.
 *
 * Scope's own mockup (section 12) shows exactly these four: "Sessions this
 * week", "Average Sessions" (read here as average session length - a count
 * of sessions has nothing to average), "Best Streak", "Content Covered".
 * Nothing here is a new backend concept; all four are derived from
 * `GET /api/analytics/sessions`, which already existed and was unused by any
 * page before this one.
 *
 * Honest about its own limit: `items` is whatever page of history the caller
 * fetched (bounded by `limit`), not a live query of a learner's entire
 * history, so a learner with more sessions than that in a single week would
 * undercount here. That is an acceptable approximation for a dashboard tile,
 * not for anything measurement-critical.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

function dateKey(iso) {
  const ms = Date.parse(iso ?? "");
  if (Number.isNaN(ms)) return null;
  const d = new Date(ms);
  // Local calendar day, not UTC - a session finished at 11pm and one at 1am
  // the same night should not count as two different days for a learner in
  // most timezones the way a raw ISO date slice would risk near midnight.
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/**
 * Consecutive calendar days, each with at least one completed session,
 * counting backward from the most recent session's day. A gap of a day or
 * more ends the streak - it does not have to reach today; a learner who
 * studied every day last week and has not opened the app since still had a
 * real streak, and "Best Streak" is asked for as a fact about the session
 * history handed in, not "current streak as of this exact moment".
 */
function longestStreak(dayKeys) {
  if (dayKeys.size === 0) return 0;

  const days = [...dayKeys]
    .map((key) => {
      const [y, m, d] = key.split("-").map(Number);
      return new Date(y, m, d).getTime();
    })
    .sort((a, b) => b - a);

  let longest = 1;
  let current = 1;
  for (let i = 1; i < days.length; i++) {
    const gapDays = Math.round((days[i - 1] - days[i]) / DAY_MS);
    if (gapDays === 1) {
      current += 1;
      longest = Math.max(longest, current);
    } else if (gapDays > 1) {
      current = 1;
    }
    // gapDays === 0 cannot happen - `dayKeys` is a Set of unique days.
  }
  return longest;
}

export function computeDashboardStats(items, { now = new Date() } = {}) {
  const sessions = Array.isArray(items) ? items : [];

  const weekAgoMs = now.getTime() - 7 * DAY_MS;
  const thisWeek = sessions.filter((s) => {
    const ms = Date.parse(s.completed_at ?? "");
    return !Number.isNaN(ms) && ms >= weekAgoMs && ms <= now.getTime();
  });

  const durations = sessions
    .map((s) => s.duration_seconds)
    .filter((value) => typeof value === "number" && Number.isFinite(value));
  const averageDurationSeconds =
    durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : null;

  const dayKeys = new Set(
    sessions.map((s) => dateKey(s.completed_at)).filter((key) => key !== null)
  );

  const contentIds = new Set(sessions.map((s) => s.content_id).filter(Boolean));

  return {
    sessionsThisWeek: thisWeek.length,
    averageDurationSeconds,
    longestStreakDays: longestStreak(dayKeys),
    documentsCovered: contentIds.size,
  };
}

function focusedPercentageOf(item) {
  const value = item?.engagement_distribution?.focused?.percentage;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Focused percentage per session, oldest first, for the trend chart. Sessions
 * with no focus figure are skipped rather than plotted as zero.
 */
export function focusTrend(items, limit = 10) {
  const points = (items ?? [])
    .map((item) => ({
      sessionId: item.session_id,
      completedAt: item.completed_at,
      focused: focusedPercentageOf(item),
    }))
    .filter((point) => point.focused !== null && !Number.isNaN(Date.parse(point.completedAt ?? "")))
    .sort((a, b) => Date.parse(a.completedAt) - Date.parse(b.completedAt));
  return points.slice(-limit);
}

/**
 * The most recent session, summarised for the home screen. Interventions are
 * counted from the session's own metrics, so they show what was actually
 * offered, and of which type.
 */
export function latestSessionSummary(items) {
  const dated = (items ?? []).filter((item) => !Number.isNaN(Date.parse(item.completed_at ?? "")));
  if (dated.length === 0) return null;
  const latest = dated.reduce((a, b) => (Date.parse(b.completed_at) > Date.parse(a.completed_at) ? b : a));

  const byType = {};
  for (const entry of latest.intervention_metrics?.by_type ?? []) {
    byType[entry.intervention_type] = entry.total_count ?? 0;
  }
  return {
    sessionId: latest.session_id,
    completedAt: latest.completed_at,
    durationSeconds: latest.duration_seconds ?? null,
    focusedPercentage: focusedPercentageOf(latest),
    longestFocusedSeconds: latest.longest_focused_period?.duration_seconds ?? null,
    interventionTotal: Object.values(byType).reduce((sum, n) => sum + n, 0),
    interventionsByType: byType,
  };
}

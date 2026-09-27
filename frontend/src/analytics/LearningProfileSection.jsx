import { formatCount, formatDurationSeconds, formatPercentage } from "./format";
import { INTERVENTION_TYPE_LABELS } from "./labels";

/**
 * What Adaptly has learned about this learner across sessions.
 *
 * Scope 6.8: "Over multiple sessions, a learning profile is built that tracks
 * patterns over time and makes each new session more personalized." Scope 6.1
 * lists the same profile as part of what a learner's account stores.
 *
 * It was being built (#97) and acted on (#98 stops offering support that has
 * not helped this learner) but never shown, so the one thing the learner could
 * not see was the reasoning being applied to them. That is the wrong way round
 * for a system that adapts silently.
 *
 * Tone follows the same rule as the insight report: forward-looking, never
 * clinical, and never framing difficulty as a personal failing. "Has not
 * helped so far" is about the support, not about the learner.
 */

const TREND_WORDS = {
  improving: "getting easier",
  stable: "holding steady",
  declining: "harder lately",
  insufficient_data: null,
};

function Trend({ label, trend }) {
  const word = TREND_WORDS[trend];
  if (!word) return null;
  return (
    <li>
      {label}: {word}
    </li>
  );
}

export default function LearningProfileSection({ profile }) {
  const sessionsAnalyzed = profile?.sessions_analyzed ?? 0;

  // A profile needs more than one session before any "pattern over time" is
  // honest. Saying so beats showing a trend computed from a single reading.
  if (sessionsAnalyzed === 0) {
    return (
      <section aria-labelledby="learning-profile-heading">
        <h2 id="learning-profile-heading">What Adaptly has learned</h2>
        <p>
          Nothing yet — this builds up as you finish sessions, and it is what makes
          later sessions fit you better.
        </p>
      </section>
    );
  }

  const effective = profile.effective_support_methods ?? [];
  const difficulties = profile.recurring_difficulty_areas ?? [];

  return (
    <section aria-labelledby="learning-profile-heading">
      <h2 id="learning-profile-heading">What Adaptly has learned</h2>

      <p>
        Based on {formatCount(sessionsAnalyzed)} finished session
        {sessionsAnalyzed === 1 ? "" : "s"}.
      </p>

      <ul>
        {profile.average_focus_percentage !== null &&
          profile.average_focus_percentage !== undefined && (
            <li>
              Typical focused time: {formatPercentage(profile.average_focus_percentage)}
            </li>
          )}
        {profile.average_session_duration_seconds !== null &&
          profile.average_session_duration_seconds !== undefined && (
            <li>
              Typical session length:{" "}
              {formatDurationSeconds(profile.average_session_duration_seconds)}
            </li>
          )}
        <Trend label="Focus over time" trend={profile.focus_trend} />
        <Trend label="Getting back on track" trend={profile.recovery_trend} />
      </ul>

      {effective.length > 0 && (
        <>
          <h3>What tends to help you</h3>
          <ul>
            {effective.map((method) => (
              <li key={method.intervention_type}>
                {INTERVENTION_TYPE_LABELS[method.intervention_type] ??
                  method.intervention_type}
                {" — helped "}
                {method.effective_count} of {method.times_used} time
                {method.times_used === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
        </>
      )}

      {difficulties.length > 0 && (
        <>
          <h3>Worth another look</h3>
          <ul>
            {difficulties.map((area) => (
              <li key={area.area_key}>
                {area.label}
                {" — came up in "}
                {area.session_count} session{area.session_count === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

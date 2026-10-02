import { Brain, Lightbulb, Target, TrendingDown, TrendingUp } from "lucide-react";

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

const TREND_ICONS = { improving: TrendingUp, stable: Target, declining: TrendingDown };

function Trend({ label, trend }) {
  const word = TREND_WORDS[trend];
  if (!word) return null;
  const Icon = TREND_ICONS[trend] ?? Target;
  return (
    <li className="flex items-center gap-2">
      <Icon size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
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
      <section aria-labelledby="learning-profile-heading" className="mb-4">
        <h2
          id="learning-profile-heading"
          className="flex items-center gap-1.5 text-lg font-semibold mb-2"
        >
          <Brain size={16} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
          What Adaptly has learned
        </h2>
        <p className="text-muted">
          Nothing yet — this builds up as you finish sessions, and it is what makes
          later sessions fit you better.
        </p>
      </section>
    );
  }

  const effective = profile.effective_support_methods ?? [];
  const difficulties = profile.recurring_difficulty_areas ?? [];

  return (
    <section aria-labelledby="learning-profile-heading" className="mb-4">
      <h2
        id="learning-profile-heading"
        className="flex items-center gap-1.5 text-lg font-semibold mb-2"
      >
        <Brain size={16} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
        What Adaptly has learned
      </h2>

      <div className="rounded-card border border-line bg-surface shadow-card p-4">
        <p className="mt-0 mb-2 text-sm text-muted">
          Based on {formatCount(sessionsAnalyzed)} finished session
          {sessionsAnalyzed === 1 ? "" : "s"}.
        </p>

        <ul className="list-none p-0 m-0 space-y-1.5 text-sm text-ink mb-3">
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
          <div className="mb-3">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold mb-1.5">
              <Lightbulb size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
              What tends to help you
            </h3>
            <ul className="list-none p-0 m-0 space-y-1 text-sm text-ink">
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
          </div>
        )}

        {difficulties.length > 0 && (
          <div>
            <h3 className="flex items-center gap-1.5 text-sm font-semibold mb-1.5">
              <Target size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
              Worth another look
            </h3>
            <ul className="list-none p-0 m-0 space-y-1 text-sm text-ink">
              {difficulties.map((area) => (
                <li key={area.area_key}>
                  {area.label}
                  {" — came up in "}
                  {area.session_count} session{area.session_count === 1 ? "" : "s"}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

# Issue #33 — Module 8 Multi-Session Learning Profile (plain-English summary)

## What this does

This is the piece of Module 8 that looks across a learner's *entire history*
of completed sessions — not just one — and works out patterns worth
remembering: is their focus generally improving? Does a particular kind of
support (a break suggestion, a simplified paragraph) actually tend to help
them specifically? Is there a section of content that keeps giving them
trouble session after session?

It takes a list of already-computed session summaries (the Issue #26/#28
output — never raw webcam/chat data) for one learner and produces one
`learning-profile.schema.json`-shaped document.

## Where this fits — and what it deliberately does NOT do

```
Issue #28 (finalization)  ->  many session summaries saved over time
                                          |
                    Issue #33 (THIS issue): build_learning_profile()
                                          |
                          a single learning-profile document
                                          |
              (a LATER issue would persist this and wire it into
               GET /api/analytics/learning-profile — not this one)
```

Just like Issue #26 built the pure single-session metric engine and left
persistence (#27), orchestration (#28), and the API (#29) as separate later
issues, this issue builds **only** the pure cross-session aggregation
function — `backend/app/analytics/domain/learning_profile.py`. It:

- takes a plain Python list of session summaries and a `user_id`
- returns a plain dict — no MongoDB, no FastAPI, nothing async
- never reads or writes the `LearningProfileRepository` (built in #27, still
  waiting for a real caller)
- never touches `GET /api/analytics/learning-profile` (still serving
  `routes._placeholder_learning_profile()`, unchanged by this issue)

Wiring the two together (compute a profile, save it, serve it for real) is
future work, not part of this issue's scope.

## A contract vs. issue-text mismatch, resolved by following the contract

Issue #33's own description talks about a "longest-focused-period trend"
and an "average recovery-duration trend" as if those were separate profile
fields. The actual shared contract
(`shared/contracts/learning-profile.schema.json`, `additionalProperties:
false`) has no such fields — only one `focus_trend` and one `recovery_trend`
enum (`improving | stable | declining | insufficient_data`). Per CLAUDE.md
6.3 ("existing contracts are authoritative... contract changes only happen
through an explicit, deliberate issue"), this implementation computes
exactly what the schema defines. `focus_trend` is derived from the
focused-percentage series across sessions; `recovery_trend` from the
recovery-rate series. No new fields were added to the contract.

## The decision CLAUDE.md flagged as still open: the evidence threshold

CLAUDE.md section 6.6 explicitly called out that
`effective_support_methods`'s minimum-evidence threshold "has intentionally
not been finalized — must be defined via config/metric-version/tests, not
invented silently." This issue makes that decision:

- **`minimum_evidence_count_for_effective_support` = 3** — a support type
  needs at least 3 evaluable outcomes (effective + ineffective, excluding
  unknown) across the learner's history before it can be called "effective."
  Two clean successes in a row is not evidence of a pattern.
- **`effective_support_min_rate` = 0.6** — even with enough evidence, it
  must have helped at least 60% of the time. A coin-flip 50% success rate is
  not something to actively recommend.

Both live on `LearningProfileConfig`, both are covered by tests at the exact
boundary (2 vs. 3 evaluable outcomes; a rate just below vs. at 0.6), and a
support type that doesn't clear the bar simply doesn't appear in
`effective_support_methods` — it can still show up in the richer,
un-gated `intervention_effectiveness_by_type` list.

## Other judgment calls made explicit (not invented silently)

- **`critical_section_aggregates.average_focus_percentage`**: session
  summaries record critical-section *focused seconds* and an *engagement
  rate*, but nothing resembling a critical-section-scoped focus percentage
  to average directly. Rather than fabricate a missing denominator, this is
  computed as the average of each session's overall focused-percentage,
  restricted to sessions that actually had at least one critical section.
- **`recurring_difficulty_areas`**: derived only from repeated
  `struggling`/`fatigued` timeline segments tied to the same
  `(content_id, chunk_id)` pair, appearing in at least 2 sessions
  (`minimum_recurring_session_count`). Intervention records were
  deliberately *not* used as a second difficulty signal, since an
  intervention's own `triggering_engagement_state` already reflects the
  same underlying engagement-state signal — combining both would double
  count one event. `label` falls back to the raw `chunk_id` string, since
  Module 8 has no chunk title text (that's Module 2's content metadata) —
  a known limitation, not an oversight.
- **`data_quality.flags`**: profile-level flags are either computed
  directly from cross-session facts (`insufficient_sessions`,
  `inconsistent_metric_versions`, `insufficient_critical_section_data`), or
  *propagated* from the per-session flags Issue #26 already computed, when a
  majority (`majority_flag_threshold` = 0.5) of the *relevant* sessions
  carried that flag (`sparse_engagement`, `missing_intervention_outcomes`,
  `incomplete_assistant_metadata`). Nothing is re-derived from data this
  layer doesn't have access to (raw events).
- **The profile's own `metric_version`** is always the current engine
  version (`METRIC_VERSION`, "1.0" today) — separate from whatever
  `metric_version` each input session happened to be computed under. If
  those differ across a learner's history, `inconsistent_metric_versions`
  is flagged rather than silently mixing incompatible calculation rules
  (CLAUDE.md 6.5 rule #4).

## Small-sample caution (CLAUDE.md 6.5, rule #7)

Every trend calculation checks `minimum_sessions_for_trend` (default 3)
*qualifying* data points before ever returning `"improving"` or
`"declining"` — below that, always `"insufficient_data"`. "Qualifying" is
deliberately not the same as "sessions analyzed": a session with no
interventions contributes a `null` recovery rate, which is excluded from
the recovery-trend calculation entirely rather than counted as a 0%
recovery rate (which would fabricate a decline out of sessions that simply
didn't need any support).

Trends are calculated by comparing the mean of the first half of the
chronological series to the mean of the second half, against a threshold
(5 percentage points for focus, 0.15 for recovery rate) — simple, evenly
weighted (using unrounded means, so exactly two events per session
never dominate the read), and deterministic.

## Zero-session behavior

`build_learning_profile(user_id, [], computed_at=...)` returns exactly the
same shape (and the same values, aside from the injected `computed_at`) as
`routes._placeholder_learning_profile()` — this is how API-shape
compatibility (an explicit acceptance criterion) is proven without touching
`routes.py` at all: a learner with zero completed sessions and a learner
whose profile hasn't been computed yet are the same state, by design.

## Privacy

The function's only parameters are `user_id`, a list of session summaries,
`computed_at`, and a config object — there is no parameter through which a
webcam frame, dense facial landmark, raw gaze coordinate, or chat transcript
could reach this code, since session summaries (Issue #26's output) never
carry those fields either. Tests assert both the function's exact parameter
list and that no raw-biometric field name appears anywhere in the module's
executable code.

## Testing

`backend/tests/analytics/test_learning_profile.py` — 42 tests, pure Python,
no MongoDB/FastAPI: zero-session shape and contract match; session counting
and chronological ordering; deterministic recalculation regardless of input
order; average duration/focus; focus-trend and recovery-trend
(insufficient/improving/declining/stable, and the "nulls are excluded, not
zero" rule); cross-session intervention-effectiveness aggregation (sums
correctly, excludes `unknown` from the rate denominator, omits never-used
types); the effective-support-methods evidence-threshold boundary (both the
count and the rate); assistant-usage patterns (preferred mode: single,
mixed, unknown; per-session averaging); recurring-difficulty-area detection
(one session doesn't count, two does; wrong states are ignored; missing
chunk IDs are ignored); critical-section aggregates (scoped only to
sessions that had any); every `data_quality` flag (direct and propagated);
and the realistic multi-session profile against the real
`learning-profile.schema.json` via the same hand-rolled schema validator
`test_metrics.py` already uses.

Command: `python -m pytest backend/tests/analytics/ -q`
Result: **161 passed** (119 pre-existing + 42 new).

## Known limitations

- **No persistence or API wiring.** `LearningProfileRepository` (#27) and
  `GET /api/analytics/learning-profile`'s placeholder (#29) are unchanged.
  A future issue needs to: fetch a learner's summaries via
  `SessionAnalyticsRepository.list_by_user()`, call
  `build_learning_profile()`, save the result via
  `LearningProfileRepository.save()`, and decide when recomputation is
  triggered (on each session finalization? on demand at read time? on a
  schedule?) — none of that is decided here.
- **`recurring_difficulty_areas` has no human-readable label.** `label`
  is the raw `chunk_id`. Attaching a real section title requires content
  metadata Module 8 doesn't own (Module 2's job).
- **No correlation ID between assistant messages**, same open gap already
  documented for the single-session engine (CLAUDE.md 6.6) — assistant
  usage here is aggregated as independent counts, not paired
  question/answer exchanges.
- **Flag propagation uses a simple majority threshold (50%)**, not a
  statistically rigorous test. This is a deliberately simple, auditable
  rule rather than a more complex model — consistent with keeping learning
  profile calculations transparent and reproducible.

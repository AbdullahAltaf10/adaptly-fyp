# Module 8 Analytics Contracts

Module 8 uses five versioned contracts in `shared/contracts/`:

- `intervention-event.schema.json` records why and how Module 4 delivered an intervention and the observed outcome.
- `assistant-event.schema.json` records Module 5 interaction metadata without message text.
- `session-summary.schema.json` contains the deterministic post-session metrics calculated from session and event data.
- `analytics-report.schema.json` tracks the approximately 150-word Gemini-generated or deterministic fallback insight report.
- `learning-profile.schema.json` contains derived patterns across multiple completed sessions.

## Time and event ordering

All timestamps use JSON Schema `date-time` values and should be emitted as timezone-aware ISO 8601 strings, preferably UTC. Producers must assign unique event IDs. Consumers order events by `timestamp` and use the event ID as a deterministic tie-breaker; implementations should retain a server receipt time separately if clock-skew handling is required. Missing intervals must be represented as `unknown`, not inferred as focused.

## Unknown data and recovery

Unknown or unavailable observations use an explicit `unknown` enum value or `null`, as allowed by each field. Zero is reserved for a measured zero.

Recovery starts at the exposure or use milestone defined for that intervention type and metric version—for example, `displayed` for an automatic adaptation or `accepted`/`completed` for learner-initiated support. It completes at the first sustained `recovered` or `focused` state. If recovery is not observed, `recovery_timestamp` and `recovery_duration_seconds` remain `null`. Average recovery time is calculated only from observed recoveries; it is `null` when none exist.

An intervention is effective when it is used and followed by sustained improvement within the configured observation window without a competing intervention. Unobserved or ambiguous outcomes remain unknown and are excluded from the effectiveness-rate denominator. Application logic must validate that total, effective, ineffective, and unknown counts are internally consistent.

## Intervention semantics

The normal lifecycle is `offered` → `displayed` → `accepted`/`completed`. An intervention can instead become `dismissed` or `failed`; not every intervention passes through every state. `reason_code` is the machine-readable analytics category, while `reason` is a learner-safe human-readable explanation.

`helped` is `true` when observed evidence indicates benefit, `false` when observed evidence indicates no benefit, and `null` when the outcome could not be determined. The separate `outcome` field preserves unknown and unobserved outcome categories.

## Metric conventions

Fields named `percentage` use a 0–100 scale. Fields ending in `_rate` use a 0–1 scale.

When a session has no critical sections, `critical_section_count` and `engaged_section_count` are `0`, `engagement_rate` is `null`, and `focused_duration_seconds` is `0`. The null rate means not applicable, not 0% engagement.

`effective_support_methods` is an interpreted set of support methods supported by sufficient repeated evidence, not a duplicate of raw intervention statistics. Application logic must apply an agreed minimum evidence/sample rule and must not infer an effective method from a single successful intervention.

## Assistant event conventions

For assistant-direction events, `input_mode` should normally be `not_applicable` and `suggested_question_used` should normally be `false`. For learner-direction events, `response_mode` should normally be `not_applicable`.

## Report states

- `pending`: `report_text`, model fields, and `generated_at` are `null`; `generation_method` is `none` and `fallback_used` is `false`.
- `generated`: report text and generation time are present, `generation_method` is `gemini`, and `fallback_used` is `false`.
- `fallback_generated`: report text and generation time are present, `generation_method` is `deterministic_fallback`, and `fallback_used` is `true`.
- `failed`: report text and `generated_at` are normally `null`, `fallback_used` is `false`, and `error_code` is populated where available. `generation_method` is normally `none` unless the implementation retains the method actually attempted.

Reports never store stack traces, prompts, secrets, API keys, or biometric telemetry.

## Versioning

`schema_version` describes data shape. `metric_version` describes calculation rules, including event-gap, sustained-state, recovery-window, and effectiveness definitions. Recalculated summaries and profiles must retain the metric version used so results remain reproducible.

## Privacy

Analytics contracts contain derived states and interaction metadata only. They must not contain webcam frames, recordings, dense facial landmarks, full chat transcripts, full document text, API keys, prompts, or unnecessary personal information. Module 11 exports must replace learner/session identifiers with scoped pseudonymous or aggregate identifiers and apply appropriate aggregation thresholds.

## Module relationships

- Module 3 supplies timestamped engagement events used for timelines, focused periods, recovery, and critical-section engagement.
- Module 4 supplies intervention events, reasons, delivery states, and outcomes.
- Module 5 supplies analytics-safe assistant events and modality metadata.
- Module 8 calculates session summaries, insight reports, and multi-session learning profiles.
- Module 10 consumes versioned session-level presence, critical-section, recovery, and assistant-engagement metrics.
- Module 11 consumes anonymized chunk-level difficulty and intervention-effectiveness aggregates, never raw biometric or chat data.

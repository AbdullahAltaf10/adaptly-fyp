# Issue #72 — Module 10 Compliance Report Contract and Engagement Quality Score Engine (plain-English summary)

## What this does

This is the foundation of Module 10: a new shared contract describing what a
compliance attestation report looks like, and a pure function that computes
the numeric heart of that report — the Engagement Quality Score — from one
already-computed Module 8 session summary.

It takes a session summary (the Issue #26/#28 output — never raw events, and
never anything the summary itself doesn't already carry) and produces a
score-related fragment: an overall 0-100 score (or `null` when there isn't
enough evidence), and a breakdown of which of the four components that went
into it, which were left out, and why.

## Where this fits — and what it deliberately does NOT do

```
Module 8 (finalize_session) -> one saved session summary
                                          |
                    Issue #72 (THIS issue): build_engagement_quality_score()
                                          |
                    {score_version, status, engagement_quality_score,
                     components, excluded_components}
                                          |
              (Issue #73 combines this with critical-section evidence
               into one full, contract-shaped compliance report --
               not this issue's job)
```

Just like Module 8's Issue #26 built the pure metric engine and left
persistence, orchestration, and the API for later issues, this issue builds
**only** the pure scoring function —
`backend/app/compliance/domain/score.py`. It:

- takes a plain Python mapping shaped like `session-summary.schema.json`
- returns a plain dict — no MongoDB, no FastAPI, nothing async
- never touches `report_id`, `critical_sections`, or any other
  report-envelope field — those are Issue #73's report builder's job
- never reads or writes anything in `backend/app/compliance/persistence`
  (doesn't exist yet — Issue #74)

## The four score components

Each is normalized to a 0-1 ratio before being expressed as an integer
0-100, and each has its own "not applicable" condition — never a fabricated
zero when the underlying signal simply doesn't exist for this session:

- **`attentional_presence`** — `(focused + recovered duration) / (session
  duration - unknown duration)`. Not applicable when that denominator is 0
  (no known-state time exists at all — an extremely sparse or
  all-unknown session).
- **`critical_section_engagement`** — the session summary's own
  `critical_section_engagement.engagement_rate`. Not applicable when
  `critical_section_count` is 0. This is the *normal* state for every real
  session today, since Module 9 (which tags chunks as critical) doesn't
  exist yet — not a data-quality problem to flag loudly.
- **`recovery_rate`** — the session summary's `recovery_metrics.recovery_rate`.
  Not applicable when that's `null` (no interventions were eligible for
  recovery measurement).
- **`chatbot_engagement`** — see "A decision made explicit" below.

## A decision made explicit: `chatbot_engagement`'s formula

The task that produced this issue asked for "the share of the learner's
chat exchanges that got a successful response." That phrasing assumes chat
exchanges can be paired up — but `assistant-event.schema.json` has no
correlation ID linking one learner message to the response it triggered
(a documented, intentionally-unresolved Module 8 gap — CLAUDE.md, renamed
to PROJECT_CONTEXT.md by PR #64, section 6.6 gap #1). Module 8's own
`assistant_usage` metrics already work around this the same way: counting
learner messages and successful assistant responses as independent totals,
not paired exchanges.

Given that, this issue computes `chatbot_engagement` as
`successful_interaction_count / learner_message_count`, clamped to a
maximum of 1.0 (so an edge case with more assistant turns than learner
turns in one session can't push the ratio over 100%). This is a
**conservative proxy**, not an exact per-exchange rate, and is documented as
a decision needing Abdullah's confirmation rather than something settled
silently. It is `not_applicable` — never 0 — whenever the learner sent no
assistant messages, since no chat activity in a session is neutral
information, not evidence of disengagement.

## Weighting and re-normalization

All four components start at an equal weight of 0.25 (`ScoreConfig`, named
fields, not scattered literals). Any component that comes back
`not_applicable` is dropped entirely and listed in `excluded_components`;
the remaining components' weights are re-normalized so they still sum to
1.0 — an excluded component's original weight is never left over as an
implicit zero pulling the score down.

## Insufficient data

Two independent conditions force `status: "insufficient_data"` (score
`null`):

1. Every component ends up `not_applicable` — nothing left to score.
2. The source session summary's own `data_quality.has_sufficient_data` is
   `false` — even if some components were individually computable, the
   underlying session data wasn't trustworthy enough to build a compliance
   figure on top of it. In this case the per-component breakdown still shows
   what *would* have been computed (for transparency), but
   `weight_applied` stays `0.0` on every component and the aggregate score
   is `null` — nothing from an untrustworthy session is asserted as fact.

## Versioning

`score_version` starts at `"1.0"`, tracked separately from both
`schema_version` (the contract's shape) and Module 8's `metric_version`
(the session summary's own calculation rules) — the same three-way
separation Module 8 already keeps between its schema and metric versions,
for the same reason: historical attestation reports need to stay
reproducible even if the scoring formula changes later.

## Testing

`backend/tests/compliance/test_score.py` — 17 tests, pure Python, no
MongoDB/FastAPI: all four components present and scorable; each component
individually excluded (not zero); all components excluded (falls back to
insufficient data); the `has_sufficient_data: false` override; score floor
(0) and ceiling (100); component-score rounding; weight re-normalization
after an exclusion, including a case that proves the excluded component's
weight doesn't silently count against the score; and `ScoreConfig`'s own
weight-sum validation.

`backend/tests/compliance/test_contract.py` — 3 tests validating a
complete, an insufficient-data, and a components-excluded sample report
against `shared/contracts/compliance-report.schema.json`, reusing Module
8's own hand-rolled schema validator (`assert_schema_match`) since the real
`jsonschema` package isn't installed in this environment (a pre-existing,
documented Module 8 gap, not something this issue installs a new dependency
to fix).

Command: `python -m pytest backend/tests/compliance/ -q`
Result: **20 passed** (17 + 3).

## Known limitations

- **`critical_sections` is reserved but not populated.** The contract
  defines the field; Issue #73 computes it. A report built by this issue's
  function alone is not yet a complete, storable compliance report — Issue
  #73's report builder assembles the full thing.
- **`chatbot_engagement` is a proxy, not an exact rate**, as explained above
  — flagged for confirmation, not settled.
- **No persistence or API wiring** — that's Issue #74. This function has
  never been called from a route or a repository.

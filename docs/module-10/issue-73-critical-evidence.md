# Issue #73 — Module 10 Critical-Section Attestation Evidence (plain-English summary)

## What this does

This is the piece of Module 10 that turns "how did the learner do on the
sections HR flagged as critical" into a plain verdict per section, and
combines that with Issue #72's Engagement Quality Score into one complete,
storable compliance report.

It takes a session summary's timeline segments, the session's chunk context
(the same `{chunk_id, is_critical, completed}` shape Module 8's finalization
service already builds), and the session's raw intervention events, and
returns one evidence entry per chunk flagged `is_critical: true`.

## Where this fits

```
Issue #72 (score engine)         Issue #73 (THIS issue)
build_engagement_quality_score()  build_critical_section_evidence()
        |                                    |
        +------------------+-----------------+
                           v
              build_compliance_report()
         (combines both into one complete,
          compliance-report.schema.json-shaped document)
```

## The critical-chunk lookup

Reused exactly, not reinvented: a chunk counts as critical when its
chunk-context record has `is_critical: true` — the identical condition
Module 8's own `metrics.py::_critical_section_metrics` already checks. This
issue does not build a second notion of "critical"; Module 8 and Module 10
can never disagree about which chunks matter, because they read the same
field the same way.

## Per-chunk verdicts

Each critical chunk's timeline segments (matched by `chunk_id`) are read in
chronological order (the order `timeline_segments` is already produced in)
and classified:

- **`sustained_engagement`** — every known-state segment on this chunk is
  `focused` or `recovered`.
- **`difficulty_then_recovered`** — a `drifting`/`struggling`/`fatigued`
  segment is followed, later in the same chunk's history, by a
  `focused`/`recovered` segment.
- **`difficulty_not_recovered`** — a difficulty segment exists with nothing
  positive after it.
- **`not_reached`** — no timeline segment ever references this chunk.
- **`insufficient_data`** — every segment referencing this chunk is
  `unknown`.

`unknown` segments are excluded from verdict logic entirely (not counted as
a break in engagement and not counted as difficulty) but are not thrown
away — a chunk with `focused -> unknown -> focused` still reads as
`sustained_engagement`, matching CLAUDE.md's (renamed to PROJECT_CONTEXT.md
by PR #64) rule that unknown gaps must never be read as a negative signal.

`focused_seconds` sums duration across `focused`/`recovered` segments;
`difficulty_seconds` sums duration across `drifting`/`struggling`/`fatigued`
segments; `intervention_count` counts intervention events whose `chunk_id`
matches, independent of verdict (an intervention can be recorded against a
chunk even in a `not_reached` case, if timeline data is sparse); a chunk
visited more than once (e.g. left, then returned to later) has all of its
visits combined into one entry, not one entry per visit.

## Granularity: chunk, not paragraph

Evidence is computed per **chunk** — the same unit Module 8's timeline
segments and `is_critical` already use — not per paragraph. Module 10's own
scope description asks for evidence "for every HR-tagged critical
paragraph," but Module 8 has no sub-chunk (paragraph-level) granularity to
draw on today — chunks are the finest unit `is_critical` and timeline
segments support. Building a separate paragraph-level signal here, instead
of reusing Module 8's existing chunk-level data, would put Module 10 out of
step with the data it actually has, so this issue evaluates at the chunk
level and documents the gap plainly rather than pretending a finer grain
exists. (This is unrelated to Module 11's own paragraph-level "difficulty
heatmap," which is a separate concept this issue does not implement.)

## Known limitation

`is_critical` is never `true` in the live system today — Module 9, which
owns that tagging, does not exist yet (see `backend/app/intervention/content.py`,
which documents the same gap for Module 4). This means `critical_sections`
is an empty list for every real session until Module 9 ships. Every verdict
in this issue's tests is exercised using fixtures with `is_critical: true`
chunks; this is the expected, documented state, not a bug to work around.

## Testing

`backend/tests/compliance/test_critical_sections.py` — 11 tests: each
verdict individually; unknown segments being ignored rather than breaking
continuity; multiple critical chunks each getting their own correct
verdict in one session; non-critical chunks being excluded entirely; a
chunk revisited after leaving and returning combining both visits correctly
(including intervention counts); and both `None` and empty chunk-context
inputs returning an empty list rather than erroring.

`backend/tests/compliance/test_report.py` — 4 tests for
`build_compliance_report()`: the combined score + evidence shape; an empty
critical-section list producing a valid report, not an error; and the full
combined report (with and without critical sections) validating against
`compliance-report.schema.json`.

Command: `python -m pytest backend/tests/compliance/ -q`
Result: **35 passed** (17 score-engine + 3 score-only contract, both carried over
from Issue #72, plus 11 new critical-section tests + 4 new combined-report tests
in this issue).

## Known limitations

- **No persistence or API wiring** — that's Issue #74. `report_id` and
  `generated_at` are still caller-injected parameters, same as Issue #72's
  `build_engagement_quality_score`.
- **Paragraph-level granularity does not exist**, as explained above.

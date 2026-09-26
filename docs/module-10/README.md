# Module 10 — Compliance Attestation Engine

## What this module is for

Module 10 is the part of Adaptly that turns a learner's Module 8 session
summary into something an HR administrator can point to as evidence of
engagement: a single Engagement Quality Score (0-100), a breakdown of what
went into that score, and — for any section of the material HR has tagged
as critical — a plain-language read on whether the learner actually engaged
with it. Module 10 doesn't watch a session happen and doesn't calculate any
of its own raw metrics; it reads Module 8's already-computed, already
privacy-safe session summary and builds an attestation report on top of it.

Everything Module 10 produces inherits Module 8's privacy and honesty rules:
no raw webcam data, no chat transcripts, and — critically — no fabricated
numbers. If a signal can't be measured for a session (no critical sections
were tagged, no interventions were eligible for recovery, the learner sent
no chat messages), that piece is left out of the score and shown as "not
applicable," never silently scored as zero.

## Progress at a glance

| Issue # | Title | Status | Detail doc |
|---|---|---|---|
| 72 | Module 10 compliance report contract and Engagement Quality Score engine | ✅ Done | [issue-72-score-engine.md](issue-72-score-engine.md) |
| 73 | Module 10 critical-section attestation evidence | ⬜ Not started | — |
| 74 | Module 10 compliance report storage and API | ⬜ Not started | — |
| 75 | Module 10 attestation report views (frontend) | ⬜ Not started | — |
| 76 | Generate the compliance report automatically at session end (blocked) | ⬜ Blocked — issue only, not implemented | — |

## How the pieces fit together

```
Module 8 — finalize_session()
     |
one saved, versioned session summary
(engagement %, recovery rate, assistant usage, critical-section
 engagement, data-quality flags, ...)
     |
     v
Issue #72 — Engagement Quality Score engine
(pure function: session summary -> score, per-component
 breakdown, exclusions -- no storage, no API)
     |
     v
Issue #73 — Critical-section evidence + report builder
(per-critical-chunk verdicts from timeline segments and
 interventions, combined with #72's score into one full,
 contract-shaped compliance report)
     |
     v
Issue #74 — Storage and API
(persist one report per session; owner or hr_admin can fetch it;
 hr_admin can list; generation is idempotent, never silently
 recalculated)
     |
     v
Issue #75 — Frontend views
(employee's own report; a minimal hr_admin list/detail view;
 the same learner-safe, non-clinical wording rule Module 8 uses)
     |
     v
Issue #76 — Auto-generate at session end (BLOCKED)
(depends on Module 8's own Issue #34 landing first, and on
 Sibtain's agreement, since it touches his engagement routes)
```

In short: Module 8 computes what happened in a session; Module 10 decides
what that means for compliance, evidences it against any critical sections
HR cares about, stores and serves that decision, and shows it back to both
the learner and HR — without ever inventing a number the underlying data
doesn't support.

## Decisions made along the way (not invented silently)

- **`chatbot_engagement`'s formula.** The assistant-event contract has no
  correlation ID pairing a learner's message to its response (a documented
  Module 8 gap — CLAUDE.md, renamed to PROJECT_CONTEXT.md by PR #64, section
  6.6 gap #1), so an exact "share of chat exchanges answered successfully"
  cannot be computed. This uses `successful_interaction_count /
  learner_message_count` (clamped to 1.0) as the most conservative available
  proxy, and is `not_applicable` — never 0 — when the learner sent no
  assistant messages at all. Flagged for Abdullah's confirmation rather than
  treated as settled.
- **Equal component weights (0.25 each), re-normalized on exclusion.** No
  component is assumed more important than another without a stated reason
  to believe so; dropping a component redistributes its weight across the
  rest rather than letting it silently count as a zero.
- **Critical-section evidence is per chunk, not per paragraph** — see
  [issue-73's doc] once it exists for the full reasoning; Module 8 has no
  paragraph-level granularity to draw on today.

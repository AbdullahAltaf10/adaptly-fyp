# Module 8 — Session Analytics & Insight Reporting

## What this module is for

Module 8 is the part of Adaptly that turns everything that happened during a
study session into something useful to look back on. While a learner
studies, other parts of the app are watching engagement (Module 3) and
offering help like simplifying text or suggesting a break (Module 4), and
the chatbot is answering questions (Module 5). Module 8 doesn't do any of
that itself — instead, once a session is over, it takes the record of what
happened and turns it into clear numbers and, eventually, a friendly written
summary: how much of the session the learner spent focused, whether the
help offered actually worked, how they used the assistant, and whether
anything about the data collection was incomplete. Those numbers then feed
the learner's own dashboard, and later feed Modules 10 and 11 (compliance
reporting and document-quality insights for the HR/enterprise side of the
product).

Everything Module 8 stores is privacy-safe by design: no webcam footage, no
facial-tracking detail, no full chat transcripts — only derived, summary-
level information.

## Progress at a glance

| Issue # | Title | Status | Detail doc |
|---|---|---|---|
| 25 | Define Module 8 analytics contracts | ✅ Done | *(contracts — see `shared/contracts/` and `docs/api/module-8-analytics-contracts.md`)* |
| 26 | Build Module 8 analytics metric engine | ✅ Done | [issue-26-metric-engine.md](issue-26-metric-engine.md) |
| 27 | Add Module 8 analytics persistence and indexes | ✅ Done | [issue-27-persistence.md](issue-27-persistence.md) |
| 28 | Implement Module 8 session finalization and summary computation | ✅ Done | [issue-28-finalization.md](issue-28-finalization.md) |
| 29 | Build Module 8 analytics and session history APIs | ⬜ Not started | — |
| 30 | Build Module 8 post-session analytics dashboard shell | ⬜ Not started | — |
| 31 | Add Module 8 engagement timeline and intervention log | ⬜ Not started | — |
| 32 | Implement Module 8 Gemini insight report and fallback | ⬜ Not started | — |
| 33 | Build Module 8 multi-session learning profile | ⬜ Not started | — |
| 34 | Integrate Module 8 with Modules 3, 4, and 5 | ⬜ Not started | — |

## How the pieces fit together

```
 Modules 3 / 4 / 5                Issue #27                  Issue #26
 (produce raw events)          (persistence layer)        (metric engine)
 engagement / intervention /  ──────►  MongoDB   ◄──── reads back events
 assistant events, sessions             │                    │
                                         │                    │ pure math,
                                         │                    │ no database
                                         ▼                    ▼
                                  Issue #28 — Finalization Service
                                  (runs when a session ends: checks the
                                   session is real/eligible, works out its
                                   duration, loads its events, calls the
                                   metric engine, saves the result, marks
                                   the session "completed")
                                         │
                                         ▼
                              One saved, versioned session summary
                              (engagement %, recovery rate, assistant
                               usage, data-quality flags, ...)
                                         │
                     ┌───────────────────┼────────────────────┐
                     ▼                   ▼                    ▼
              Issue #29 — APIs   Issue #30/#31 —      Issue #32 — Gemini
              (serve summaries    Dashboard shell &     insight report
               + history to        timeline/log UI      (separate step,
               the frontend)                             numeric analytics
                                                          don't depend on it)
                                         │
                                         ▼
                          Issue #33 — Multi-session learning profile
                          (patterns across all of a learner's sessions)
                                         │
                                         ▼
                     Issue #34 — Real integration with Modules 3/4/5
                     (replace test/mock event data with the real thing)
```

In short: raw events flow in, the metric engine turns them into numbers
without ever touching a database, the persistence layer is the only thing
that talks to MongoDB, and the finalization service is the conductor that
calls both of those at the right moment when a session ends. Everything
after that (APIs, dashboard, AI insight text, cross-session profiles, and
finally wiring in the real Modules 3/4/5 instead of test data) is still
ahead.

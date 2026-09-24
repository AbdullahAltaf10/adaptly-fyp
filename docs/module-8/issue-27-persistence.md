# Issue #27 — Module 8 Analytics Persistence (plain-English summary)

## What this does

This is the piece of Module 8 that actually **saves things to the database**.

Issue #26 built a calculator: give it a session's raw events, and it works out
things like "how much of the session was the learner focused," "did the
breaks actually help," and "how much of the assistant did they use." But a
calculator on its own doesn't remember anything — it just computes an answer
and forgets it the moment the function returns.

Issue #27 adds the storage layer underneath that calculator. It defines:

- **Where** each kind of data gets saved in MongoDB (which collection).
- **What exactly** is allowed to be saved (and, just as important, what is
  never allowed to be saved).
- **How** repeated or duplicate submissions are handled so nothing gets
  double-counted.
- **What lookups** the rest of the app can do (e.g. "give me everything that
  happened in session X," or "give me this learner's session history").

Nothing about how the numbers are calculated changed. This work sits
strictly *underneath* Issue #26 — the calculator (`backend/app/analytics/domain/metrics.py`)
still knows nothing about MongoDB and was not touched.

## What's stored, and why

Seven kinds of data, each in its own collection:

1. **Sessions** — one record per study session: who, what content, when it
   started/ended, how it's going.
2. **Engagement events** — the steady stream of "focused / drifting /
   struggling / fatigued / recovered" readings produced while the learner
   studies. This is what the Issue #26 calculator turns into a timeline.
3. **Intervention events** — every time the app offered help (simplify,
   summarize, suggest a break, etc.), and what happened afterward.
4. **Assistant events** — metadata about chatbot interactions (typed vs.
   voice, how it went) — **not** the actual conversation.
5. **Chunk progress** — which reading sections a learner entered/finished,
   and whether that section was flagged as important ("critical").
6. **Session analytics (summaries)** — the finished output of the Issue #26
   calculator, saved so the dashboard doesn't have to recompute it from
   scratch every time someone opens it.
7. **Learning profiles** — one record per learner summarizing patterns across
   *all* their sessions (e.g. "focus has been improving," "breaks tend to
   help this learner").

Each collection only stores the fields listed in the project's shared
contracts (the agreed-upon data shapes in `shared/contracts/`) — nothing
extra is ever kept. Concretely, this code strips out any unexpected field
before saving, so even if something upstream accidentally attached, say, a
webcam frame or a full chat message to an event, it gets silently dropped
before it ever reaches the database. This was tested directly: a test
deliberately tries to save a fake "video frame" and a fake chat message, and
confirms neither one makes it into storage.

## What the indexes are for

An index is just a shortcut the database uses so it doesn't have to scan
every single record to answer a common question. The indexes added here
match the patterns the app will actually need once the dashboard and APIs
exist:

- "Find this one session by its ID" (fast lookup, and also guarantees no two
  sessions can accidentally share the same ID).
- "Find everything that happened in this session, in time order" — needed to
  rebuild a timeline for the dashboard.
- "Find all of this learner's sessions" — needed for session history and the
  multi-session learning profile.

## How duplicates are handled

Real systems retry things. A flaky network connection might cause the same
engagement reading to get sent twice, or someone might click "generate
report" on a session that already has one. This layer is built so that never
causes a problem:

- Every event has its own natural ID (e.g. `event_id`). Saving the same ID
  twice **overwrites** the same record instead of creating a second copy —
  so duplicate submissions can never inflate the numbers.
- A session's computed summary is saved once per session, and re-running the
  calculation for that same session just replaces the existing summary
  rather than adding another one next to it.
- A learner's learning profile works the same way — recomputing it replaces
  the old version instead of piling up.

This was directly tested: the test suite saves the same event or summary
multiple times in a row and checks that only one copy ever ends up in
storage.

## How it connects to Issue #26

```
Issue #26 (calculator)                    Issue #27 (this work)
------------------------                  ----------------------
Raw events in  →  build_session_summary()  →  Persistence layer saves the
                   (pure math, no database)     raw events AND the finished
                                                 summary to MongoDB
```

Issue #26's code has zero knowledge that MongoDB exists — it just takes
plain data in and returns plain data out. Issue #27's code is the only part
that knows about the database, and it calls Issue #26's calculator, then
saves what comes back. This separation means the math can be tested (and
trusted) completely on its own, and the storage logic can be swapped or
upgraded later without touching the calculations at all.

## How this was tested without a real database

Real MongoDB wasn't used for testing. Instead, the tests use a fake,
in-memory stand-in called `mongomock` that behaves like MongoDB from the
code's point of view, but lives entirely in memory and disappears when the
test ends. This means the tests are fast, don't need any setup, and don't
risk touching real data — but they still exercise the exact same
save/retrieve logic that will run against the real database in production.

## Known limitations (things intentionally left for later)

- **This only builds the storage layer, not the code that calls it during a
  live session.** Actually wiring this into a running FastAPI endpoint (so
  events get saved as they happen) is future work — Issues #28 and #29.
- **No automatic data cleanup (retention/expiry) yet.** The storage shape
  was designed so that raw events *could* later get an automatic expiry
  (e.g. "delete raw events after 90 days but keep the summaries forever"),
  but that expiry itself hasn't been turned on. That's a deliberate decision
  to finalize later, not an oversight.
- **"Chunk progress" doesn't have an official shared contract yet.** Sessions,
  engagement events, interventions, and assistant events all follow schemas
  the whole team agreed on. Chunk progress doesn't have one of those yet, so
  this uses a minimal, obvious set of fields (matching exactly what Issue #27
  asked for) rather than inventing a bigger design.
- **The real MongoDB connection code is untested against an actual Atlas
  database** in this pass, since Issue #27 was explicitly scoped to work
  without a live database. It follows the same connection pattern already
  documented in `backend/README.md`.
- **`ensure_indexes()` assumes the collections are either empty or already
  clean when a unique index is first created.** If duplicate data violating a
  unique constraint existed before the index was created, `create_index()`
  will raise rather than silently skip it. Not a concern yet (no live
  database has been used), but worth handling explicitly (e.g. a pre-flight
  duplicate check, or catching and reporting the error clearly) before this
  ever runs against real data.

# Issue #30 — Module 8 Dashboard Shell (plain-English summary)

## What this shows

This is the first piece of the actual screen a learner would see after
finishing a study session — the "Session summary" page. It shows, for one
completed session:

- **What you studied and when** — the content title, the date, how long the
  session lasted, and how it ended.
- **Key numbers** — the longest stretch you stayed focused, how quickly you
  tended to bounce back after being offered help, how often that help
  worked, and how much you used the assistant.
- **An engagement summary** — a simple breakdown of how the session went
  (mostly focused, some drifting, etc.), in calm, everyday language rather
  than clinical terms.
- **What support was offered**, if any, and whether it seemed to help.
- **A short written summary** of the session (eventually written by AI —
  see below).

Nothing about *how* the numbers are calculated is new here — that was
Issues #26–#29. This issue builds the screen that will eventually show
those real numbers, and gets it fully working and tested using realistic
practice data first.

## Where the mock data lives, and why

Right now, none of Module 8's real backend pieces are wired up to this
screen. Instead, this dashboard is built and tested against six realistic,
made-up example sessions, all defined in one file:
`frontend/src/analytics/mockData.js`. They cover:

1. A normal session with a mix of focus and a little difficulty.
2. A session where no extra help was ever needed.
3. A session where very little usable data was collected (the numbers are
   mostly "unknown," not "bad").
4. A session where the camera-based tracking didn't produce any data at
   all.
5. A session where everything about the numbers is fine, but the written
   AI summary specifically failed to generate.
6. A "perfect data" session where absolutely nothing is missing, used to
   check the fully-populated view.

Each one is written to match **exactly** the same data shape the real
Module 8 backend already promises to return (the official formats defined
in `shared/contracts/session-summary.schema.json` and
`analytics-report.schema.json`, and the actual API built in Issue #29).
That matters: it means this isn't guesswork data thrown together to make
the screen look nice — it's the same shape real data will arrive in, so
building and testing against it now is a faithful rehearsal for the real
thing.

## How the real backend will replace this later — without a redesign

There's exactly one place in the code that currently "pretends" to be the
backend: a small file called `useSessionAnalytics.js`. Every part of the
dashboard asks *that one function* for the session's data; nothing else in
the dashboard talks to the mock data directly.

Today, that function quietly hands back one of the six example sessions
above (with a tiny simulated delay, so the loading state is exercised
honestly). Later, when Issue #29's real API is ready to be connected, only
that one function needs to change — from "return example data" to "actually
ask the server." Nothing about how the page looks, how it's laid out, or
how any of its pieces work needs to be touched or redesigned. This was a
deliberate design goal from the start ("backend independence"), not
something worked around after the fact.

## The rule that "in-progress" sessions never show analytics

This was called out as a hard requirement, and it's treated as one: **a
session that hasn't finished yet must never show engagement numbers,
scores, or behavioral details, even by accident.**

This is enforced in two layers, not just one:

1. The dashboard checks the session's status *before* doing anything else.
   If it isn't "completed," the dashboard doesn't even ask for the
   session's numbers in the first place — it simply shows a calm "this
   session is still in progress" message and stops there.
2. Because that check happens first, none of the number-showing parts of
   the page (the overview, the key-number cards, the engagement summary,
   the support-offered list, the written summary) are ever reached while a
   session is active, paused, just created, or ended early. There's no code
   path where they could accidentally render with in-progress data, because
   they're never given the chance to run at all.

This was directly tested: the test suite deliberately gives the dashboard a
full, complete set of analytics data *while marking the session as still
active*, and confirms none of it appears on screen, and that the dashboard
never even tried to fetch it.

## Never showing a blank "0" for something that just wasn't measured

Some numbers on this page have a real, honest zero (for example, "0 pieces
of extra support were offered" genuinely means none were offered — that's
worth celebrating, not hiding). But other numbers can be **unmeasured**
rather than zero — for example, if hardly any camera data came through,
there's no honest "average recovery time" to report at all.

Every part of this dashboard is built to tell those two situations apart.
Anywhere a number genuinely cannot be known, the page says **"Not
available"** in plain words — it never quietly shows "0" or "0%" and lets
that look like a real measurement. This was tested directly as well, using
one of the six example sessions that's deliberately missing several values.

## Accessibility and tone

- The page uses a single main heading and properly nested section headings,
  so it makes sense read aloud by a screen reader, not just visually.
- Every visual bar (like the engagement breakdown) also has a written
  description next to it — nothing on this page depends on seeing a color
  or a bar length to understand it.
- Every interactive element (like the "Try again" button on a failed
  written summary) is a real, standard button, so it works naturally with
  a keyboard, not just a mouse.
- There is **no distracting animation anywhere** — the loading state is
  plain, calm text, on purpose.
- The language throughout was written to be calm and supportive.
  Difficulty during a session is never described as "failing" or
  "struggling" in front of the learner — internally, the system tracks a
  category called "struggling," but the screen itself says things like
  "working through a tough spot" instead. This isn't a style choice; it's a
  hard requirement for how this product treats neurodivergent learners.

## Folder structure decision (relevant for Issues #31–34, which build on this)

The existing frontend (merged from Modules 1–3) organizes code by feature —
`src/auth/`, `src/engagement/`, with page-level screens in `src/pages/` —
using plain inline styles (no CSS framework) and colocated test files
(`Thing.jsx` next to `Thing.test.jsx`). This issue follows that exact
pattern rather than introducing a new one:

- **`frontend/src/analytics/`** — the new Module 8 feature folder: the mock
  data, the data-fetching hook, and every reusable analytics component
  (summary cards, the overview, the engagement section, the support
  section, the written-summary section, loading/error states, and the
  active-session notice).
- **`frontend/src/pages/AnalyticsDashboard.jsx`** — the actual page, which
  composes those pieces together, matching how `StudySession.jsx` already
  works for Module 3.

Issues #31 (a fuller engagement timeline) and #33 (real cross-session
trends) should be able to add to `src/analytics/` the same way, without
needing to restructure anything already here.

## Testing

36 tests pass across the whole frontend test suite (19 already existing
from Modules 1–3, plus 17 new for this dashboard) — nothing pre-existing
broke. The new tests cover: a normal full render, the loading state, both
kinds of error state, the no-support-needed empty state, a session with
several genuinely missing values (checking "Not available" appears and a
bare 0/false never does), the failed-summary state with its retry button,
the active-session guard across every non-completed status, and basic
accessibility checks (heading structure, text alternatives for the visual
bars, and that the retry action is a real button).

## Known limitations

- **This dashboard isn't linked into the app's navigation yet.** The
  existing sign-in screen (`App.jsx`) is explicitly a temporary placeholder
  that Module 1's real frontend work will replace, not something to build
  permanent navigation on top of — so this page exists and is fully tested
  on its own, ready to be linked in once real routing exists.
- **The written AI summary is entirely mock right now** — no real Gemini
  call happens anywhere in this issue. That's Issue #32.
- **The engagement section is intentionally simple.** A full, detailed
  timeline view is Issue #31's job; this issue only shows the basic
  breakdown that's already available today.
- **The "Try again" button on a failed summary doesn't actually retry
  anything yet** — it calls a placeholder function, consistent with the
  real backend's own retry endpoint (Issue #29), which is also an honest
  stub until Issue #32 exists.

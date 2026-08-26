# Issue #26 — Module 8 Metric Engine (plain-English summary)

## What this does, and why it matters

This is the calculator at the heart of Module 8. It takes the raw stream of
things recorded during a study session — engagement readings, the help that
was offered, the chatbot interactions — and turns them into the numbers a
learner (or, later, an HR admin) would actually want to see:

- How much of the session was spent focused, drifting, struggling, fatigued,
  or recovering — and how much simply couldn't be determined.
- The longest unbroken stretch of real focus.
- Whether the help the app offered (simplify, summarize, suggest a break,
  offer the chatbot) actually seemed to work, and how long it took the
  learner to recover after being offered it.
- How the assistant was used (typed vs. voice, how often it succeeded).
- Whether the important, "critical" sections of the material actually got
  engaged with.
- Whether the data for this session was solid enough to trust, or too sparse
  /gappy to draw strong conclusions from.

Without this piece, all the app would have is a pile of disconnected
readings. This is what turns that pile into a session summary a person can
actually understand and act on.

## Why it's kept completely separate from the database ("pure function")

This calculator lives entirely on its own, with **zero knowledge that a
database, a web server, or Gemini even exist**. Give it plain data (a
session record, a list of events), and it hands back plain data (a summary)
— nothing more, nothing less. It never reads from or writes to MongoDB,
never makes a network call, never imports FastAPI.

Why that matters, in plain terms: a "pure" calculator like this is easy to
trust, because the answer only ever depends on what you fed it — run it
twice with the same input and you get exactly the same output, every time.
That means it can be tested thoroughly and quickly (no database, no
internet connection, no waiting — the whole 51-test suite for this piece
runs in a fraction of a second) and, just as importantly, it means a bug in
the database code, or an outage in Gemini, can never corrupt or distort the
actual math. The math is proven correct on its own, in isolation, and stays
that way no matter what happens around it. Issue #27 (persistence) and
Issue #28 (finalization) both call into this calculator, but neither one
was allowed to add so much as a single new import to it — that boundary was
checked directly (a "zero-diff" check) at the end of both of those pieces of
work.

## The "unknown is not zero" rule — and why it matters here

This is probably the single most important rule the calculator follows, and
it's worth explaining why it's not just a technical nitpick.

Imagine the webcam briefly loses track of the learner's face for 30 seconds
— maybe they leaned out of frame, maybe there was a brief camera glitch. If
the system just quietly treated that gap as "focused" (or as "0% engaged"),
it would be **making something up** and presenting it as fact. Multiply that
across a whole session, and the "focused" percentage on a learner's report
could be flattering-but-wrong, or unfairly harsh-but-wrong — either way,
it's a number nobody should trust, and it's exactly the kind of thing that
would undermine an accessibility-focused product built to be honest with
learners about their own attention and effort.

So instead, the calculator is strict about the difference between "we
measured this and it was zero" and "we don't actually know." A gap in
tracking becomes an explicit **`unknown`** segment on the timeline — not a
guess dressed up as "focused." A support method with no observed benefit at
all is `unknown`, not silently counted as a failure. A recovery that
couldn't be confirmed is `null` (not measured), never a fake `0` seconds.
Effectiveness rates are calculated only from the cases that could actually
be judged one way or another — an intervention with an unclear outcome
doesn't quietly drag the "success rate" down (or up); it's left out of that
particular calculation entirely and reported separately as "unknown."

The result is a report that a learner (or an auditor) can actually trust:
every number either reflects something that was genuinely observed, or is
honestly labeled as not knowable, and the two are never allowed to blur
together.

## How "did this help?" and "did they recover?" are judged

Two related but distinct questions get asked about every piece of help the
app offers:

**Did the learner recover?** After a piece of help is offered, the
calculator watches what happens next, within a limited time window (not
forever — currently about two minutes). If the learner's engagement
settles back into a solid, *sustained* focused/recovered state within that
window, that's counted as a real recovery, with a start point and duration.
A single good reading right after the intervention doesn't count on its
own — it has to hold for a couple of consecutive readings, so a brief
flicker isn't mistaken for genuine recovery. If nothing conclusive happens
in the window — or another piece of help arrives first and takes over the
window — the recovery is honestly recorded as "not observed," never as a
disguised zero.

**Was it effective?** This asks a slightly bigger question than recovery
alone. If there's a direct signal that says so (an explicit "this helped" /
"this didn't help" flag), that wins outright. Otherwise, the calculator
looks at the recorded outcome (did things improve, stay the same, or get
worse?) and falls back to "did we observe a recovery?" as a last resort.
Anything that can't be judged by any of those signals is marked `unknown`
— and, per the rule above, `unknown` cases are left out of the
effectiveness percentage rather than silently counted against (or for) it.

## Two known, unresolved gaps (deliberately left open, not bugs)

Two limitations were identified early and deliberately **not** patched over
with a guess, because fixing them properly needs a small decision at the
data-contract level first, not just a code change:

1. **No way to pair a learner's chatbot message with the assistant's
   reply.** The shared data format for assistant interactions doesn't
   currently include a "this reply answers that message" link. So instead
   of confidently saying "the assistant successfully answered 4 questions,"
   the calculator takes the conservative route: it counts *successful
   assistant responses* as a proxy, rather than claiming an exact count of
   full back-and-forth exchanges it can't actually verify. It's an
   honest approximation, clearly labeled as such, rather than an invented
   precise-sounding number.

2. **No way to record when a session was paused and resumed.** The shared
   session format only has a start time and an end time — nothing in
   between for "paused from here to here." So right now, the calculator (and
   the finalization step built on top of it, Issue #28) treats the full
   wall-clock time from start to end as the session's duration, even though
   that technically includes any paused/break time. This is a known,
   accepted limitation — not a silent miscalculation — and fixing it
   properly means first adding a place to record pauses in the shared
   session format, which is a deliberate design decision for later, not
   something to sneak in as a quick patch.

Both of these are documented so that anyone touching this code later
understands they're open questions with a known answer ("we chose the
honest, conservative approximation") rather than things nobody noticed.

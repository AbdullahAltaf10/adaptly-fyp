# Issue #28 — Module 8 Session Finalization (plain-English summary)

## What this does

This is the piece of Module 8 that runs the moment a study session actually
ends. It's the "glue" step: it takes a session that's still in progress,
closes it out properly, and produces the one official analytics summary for
that session.

Concretely, when told "finalize session X for learner Y," this code:

1. Checks the session exists at all.
2. Checks it actually belongs to that learner (not someone else's session).
3. Checks it's in a state where finishing makes sense.
4. Works out exactly how long the session lasted.
5. Pulls together everything that was recorded during the session (focus
   readings, interventions offered, chatbot usage, reading progress).
6. Hands all of that to the Issue #26 calculator to get the real numbers.
7. Saves the result and marks the session "completed."

## How it fits between #26 and #27

```
Issue #27 (storage)  →  Issue #28 (this work)  →  Issue #26 (calculator)  →  Issue #27 (storage)
  load events              orchestrate the           pure math                save the summary,
                            whole workflow                                    mark session done
```

Issue #26's calculator and Issue #27's storage code don't talk to each other
directly — neither one knows the other exists. Issue #28 is the layer in the
middle that knows about both: it fetches raw data using Issue #27's
repositories, feeds it into Issue #26's calculator, and saves what comes back
using Issue #27's repositories again. The calculator itself
(`backend/app/analytics/domain/metrics.py`) was not touched by this work at
all — confirmed with a zero-line diff, same check as Issue #27.

This new code also does **not** talk to Gemini in any way. Generating the
friendly written insight report is a separate, later step (Issue #32). This
issue only guarantees the numbers — engagement percentages, recovery rates,
and so on — get calculated and saved reliably, whether or not the AI report
ever gets generated.

## How different session situations are handled

A session can be in one of several states when "finish" is requested, and
each is handled differently on purpose, not just left to do whatever the
generic code path happens to do:

- **Active or paused** → this is the normal case. The session gets closed
  out: end time recorded, duration calculated, status flipped to
  "completed," and the summary computed and saved.
- **Already completed** → nothing gets redone. If a summary already exists
  for this session, it's simply handed back as-is. (See "Idempotency"
  below for why this matters.)
- **Abandoned** → deliberately **not** finalized the normal way. Turning an
  abandoned session into a "completed" one would misrepresent what actually
  happened, so this is rejected with a clear reason instead.
- **Never really started ("created")** → also rejected; there's nothing
  meaningful to summarize yet.
- **Doesn't exist** → a clear "not found" error, not a silent no-op.
- **Belongs to someone else** → a clear "access denied" error. This check
  happens before anything else runs, so a wrong-user request can never
  accidentally touch or change the session.

## How duration is calculated

The session's duration is: **end time minus start time**, in seconds,
computed at the moment finalization happens (not guessed, not left blank).

A few specific rules, because getting this wrong would mean a learner's
report shows a made-up number:

- **Missing or unreadable start time** → finalization refuses to guess a
  duration. It fails safely with a clear reason instead of inventing a
  number.
- **End time somehow earlier than start time** (e.g. a clock problem) → also
  refused, for the same reason. No negative or nonsensical duration is ever
  produced.
- **Paused time** → this is a known, deliberate limitation, not an oversight.
  The system doesn't currently track "the session was paused from 2:00 to
  2:15," because that information doesn't exist anywhere yet (the shared
  session format doesn't have a place to record it — this was already
  flagged as an open gap in earlier Module 8 planning). So right now, paused
  time is simply included in the total duration, the same way a wall clock
  would count it. This is safe (it never produces a *wrong-direction* or
  fabricated number) but it does mean a session paused for a long break will
  show a longer duration than the learner was actually actively studying.
  Fixing this properly needs a small addition to the shared session format
  first, which is a decision for later, not something patched in silently
  here.

## Idempotency (why finalizing twice is safe)

If "finish this session" gets sent twice — a double-click, a retried network
request, whatever — the second call does not create a second summary or
double-count anything. It recognizes the session is already finished, finds
the existing summary, and just returns it. This was directly tested: calling
finalize three times in a row for the same session still leaves exactly one
saved summary behind.

There's also a self-healing case: if a session is marked "completed" but
somehow has no summary saved (e.g. a previous attempt was interrupted after
marking the session done but before saving the summary), finalizing it again
computes and saves the missing summary instead of getting stuck.

## What happens if something goes wrong

If the calculation step itself fails for any reason (for example, corrupted
data slipping in — like an event that claims to belong to this session but
lists a different learner as its owner), the failure is handled safely:

- The session is **not** marked completed.
- No summary is saved, correct or otherwise.
- A clear "this failed, here's why" result is returned instead of crashing
  or producing a misleading "completed" summary.
- Because nothing was written, simply calling finalize again later (after
  the underlying data problem is fixed) works normally — no special cleanup
  step is needed first.

This was tested directly by deliberately planting a bad event and confirming
finalization fails cleanly, the session stays untouched, and a retry after
removing the bad event succeeds normally.

## Testing

`backend/tests/analytics/test_finalization.py` — 18 tests, using the same
in-memory `mongomock` approach as Issue #27 (no live database needed).
Covers: a normal successful finalization, repeated/duplicate finalization,
sessions with no interventions, sparse engagement data, missing optional
data (no assistant usage, no chunk-progress records), a missing session, a
cross-user access attempt, every session-state case (active, paused,
completed, abandoned, created), all three duration edge cases (paused time,
missing start time, end-before-start), a failed calculation with a safe
retry afterward, and confirmation that the session ends up in the correct
"completed" state.

Command: `python -m unittest backend.tests.analytics.test_metrics backend.tests.analytics.test_persistence backend.tests.analytics.test_finalization`
Result: **95 passed, 0 failed** (51 from Issue #26 + 26 from Issue #27 + 18 new).

## Known limitations

- **Two "finish this session" requests arriving at nearly the same moment
  (a double-click, a retried network request) could both see the session as
  still active and both compute a summary.** This is not currently prevented
  with a lock. It's not a data-corruption risk — the session record and the
  summary are both saved under fixed IDs, so the second write just overwrites
  the first with an equivalent result — but it does mean one of the two
  computations is wasted work, and it's worth adding a proper guard later.
- **Paused time is counted as elapsed time**, as explained above — a
  deliberate, documented placeholder until the session contract gets a real
  pause-interval field. Not something to quietly "fix" without that contract
  decision.
- **No API endpoint calls this yet.** This is the orchestration logic only;
  wiring a real "Finish Session" button/request to this code is Issue #29.
- **No automated retry/queue.** If finalization fails, retrying is safe and
  supported, but nothing automatically retries it — something upstream
  (Issue #29's API layer, most likely) will need to decide when to retry.
- **Cross-user access checking here is a defense-in-depth check inside
  Module 8, not a replacement for real authentication.** It assumes the
  caller has already verified who the "requesting learner" actually is
  (that's Module 1's job); this code just confirms the session it's about to
  touch actually belongs to that learner.

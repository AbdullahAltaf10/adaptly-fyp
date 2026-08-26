# Issue #29 — Module 8 Analytics APIs (plain-English summary)

## What this does

Everything Module 8 has built so far (the calculator in #26, the storage in
#27, the "close out a session" workflow in #28) has been invisible to
anyone outside the backend code — there was no way for the actual website
to ask for any of it. This issue adds that missing front door: four web
addresses (API endpoints) the frontend can call to get a learner's session
results, their session history, their overall learning trends, and to
(eventually) retry generating the AI-written summary.

In short: this is the piece that finally lets a learner's dashboard show
them something real.

## The four things you can now ask for

1. **"Show me the results for this one session"** —
   `GET /api/sessions/{session_id}/analytics`. Returns the full picture:
   how focused they were, whether the help offered worked, how they used
   the assistant, and whether the data was solid enough to trust.

2. **"Show me my past sessions"** — `GET /api/analytics/sessions`. Returns
   a list of previous sessions, most recent first, in manageable pages
   rather than all at once, with just the summary numbers for each one
   (not the full second-by-second detail — that would be a lot of data
   to send just for a list view).

3. **"Show me my overall trends"** — `GET /api/analytics/learning-profile`.
   Meant to show patterns across *all* of a learner's sessions (is their
   focus improving over time? what kind of help tends to work for them?).
   The real version of this is Issue #33's job; for now this returns an
   honest "not enough data yet" placeholder shaped exactly like the real
   thing will be, so nothing breaks or needs rewriting once #33 exists.

4. **"Try generating the AI report again"** —
   `POST /api/sessions/{session_id}/insight-report/retry`. The
   friendly, written paragraph summarizing a session (via Gemini) doesn't
   exist yet — that's Issue #32. This endpoint exists now so the *shape*
   of that feature is already in place, and it's built to guarantee it can
   never accidentally recompute or duplicate a learner's actual numeric
   results while it waits for #32 to give it real work to do.

## How "who's asking" is figured out (and why it's temporary)

Every one of these endpoints needs to know which learner is asking, so it
never shows one learner someone else's session data. Normally that comes
from a proper login system — but Module 1 (the team's login/auth work) isn't
merged into the shared codebase yet, and this work couldn't wait for it.

Rather than either blocking on that, or doing something risky like trusting
whatever user ID the frontend happens to send, this was built with exactly
one clearly-labeled placeholder: a single function whose only job is
"figure out who's asking." Right now, that function does it in a very
simple, dev-only way (it reads a special header sent with the request). But
every endpoint calls *that one function* and nothing else — none of them
ever just trust a value handed to them directly. So when the real login
system is ready, only that one function needs to be rewritten; nothing
about the four endpoints themselves has to change. This is called out
directly in the code with a "TEMPORARY" comment so nobody mistakes it for
the real thing later.

## Keeping one learner's data away from another

Two of the endpoints above are about a specific session, which means there's
a real question to answer carefully: what happens if someone asks for a
session that isn't theirs?

The answer here is deliberately strict: asking for a session that doesn't
belong to you gets **exactly the same response** as asking for a session
that doesn't exist at all. That might seem like an odd detail, but it
matters — if the app responded differently for "that's not your session"
vs. "that session doesn't exist," someone could use that difference to
figure out which session IDs are real, even without ever seeing their
contents. Giving away nothing at all is the safer choice.

## Not showing "in-progress" as if it were final

If someone asks for the analytics of a session that's still active (the
learner is mid-session, hasn't clicked "finish" yet), the app does **not**
hand back partial numbers dressed up as a final report. It clearly says
"this session hasn't finished yet" instead. This matters because a
half-finished session's numbers can be misleading on their own — someone
glancing at a dashboard mid-session shouldn't see a number that looks
final but isn't.

## Keeping session lists lightweight

The session-history list intentionally leaves out the most detailed,
"raw-ish" part of a session's results (the second-by-second timeline) —
that's a lot of data, and nobody needs it just to see a list of past
sessions. The full detail is only a click away, through the single-session
endpoint above. This also means listing a learner's whole session history
never accidentally sends more data than necessary — a small, deliberate
privacy/performance choice.

## Testing

`backend/tests/analytics/test_api.py` — 19 tests using FastAPI's own test
tools (no real server, no real database — the exact same in-memory approach
used in Issues #27 and #28). Covers: a normal successful request, a
cross-user request being denied (and proven to look identical to a
not-found request), an active session correctly being refused, unknown
sessions, ordering and pagination of the history list (including invalid
page sizes being rejected), an empty history being handled gracefully, the
learning-profile placeholder matching its official shape, the insight-report
retry stub never touching the real summary, and the full analytics response
being checked against the official session-summary format.

Command: `python -m unittest backend.tests.analytics.test_metrics backend.tests.analytics.test_persistence backend.tests.analytics.test_finalization backend.tests.analytics.test_api`
Result: **114 passed, 0 failed** (51 + 26 + 18 + 19).

## Known limitations

- **There's no real running server yet.** This issue builds the endpoints
  themselves and tests them directly; actually wiring them into a live,
  running backend application (`backend/app/main.py`) wasn't part of this
  issue's scope and doesn't exist in the repo yet — that's shared backend
  foundation work, not something to bolt on unilaterally here.
- **The temporary auth placeholder is exactly that — temporary and
  insecure by design.** It must be replaced before this ever goes near a
  real learner's data (tracked as part of Issue #34).
- **The learning-profile endpoint is a placeholder**, as explained above,
  until Issue #33 exists.
- **The insight-report retry endpoint doesn't retry anything real yet** —
  it's a stable stub shape waiting for Issue #32.

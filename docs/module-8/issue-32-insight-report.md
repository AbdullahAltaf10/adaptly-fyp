# Issue #32 — Module 8 Gemini Insight Report and Fallback (plain-English summary)

## What this does

This is the piece of Module 8 that writes the short, encouraging paragraph a
learner sees at the bottom of their post-session summary — the "AI-written
summary" the dashboard shell (Issue #30) already had a placeholder for.

Concretely, when a learner (or the dashboard, on their behalf) asks for that
written summary:

1. The learner's already-computed, numbers-only session summary (duration,
   engagement percentages, support offered, recovery rate, and so on — never
   raw events, chat transcripts, or webcam data) is turned into a prompt.
2. Gemini is asked to write ~150 words from that prompt, staying grounded in
   the numbers and using warm, non-clinical language.
3. Gemini's answer is checked before anyone sees it: is it non-empty, a
   plausible length, and free of words like "failure" or "abnormal"?
4. If Gemini is unavailable for ANY reason — no API key configured, the
   service times out, or its answer fails that check — a second, fully
   deterministic paragraph is built instead, using only the same numbers.
   The learner always gets a useful summary either way.
5. Whichever paragraph was produced is saved, along with bookkeeping
   (which method produced it, when, how many retries so far).

## Where this fits

```
Issue #28 (finalization)  →  session summary saved, insight_report_status="pending"
                                          |
                          POST .../insight-report/retry  (THIS issue, #32)
                                          |
                    build prompt from summary  ->  try Gemini  ->  validate
                                          |                           |
                                     (fails / unavailable)     (passes)
                                          |                           |
                                 deterministic fallback          use as-is
                                          |                           |
                                          +----------- save ----------+
                                                        |
                                     GET .../analytics (Issue #29) reads it back
```

`GET /api/sessions/{id}/analytics` (Issue #29) was and remains **completely
passive** — it only ever reads whatever has already been generated and saved.
The retry endpoint is the *only* place in Module 8 that ever calls Gemini or
builds the fallback. This was a hard design constraint (and is locked in by
an existing test, `test_successful_retrieval_returns_full_payload`, which
expects `{"status": "pending", "report_text": None}` immediately after
finalization with no retry call).

## Why this is standalone, not built on Module 5's Gemini code

Module 5 (the context-aware assistant) also uses Gemini, but that code lives
only on an unmerged branch (`feature/24-assistant-testing-docs`, PR #43)
that has known problems (a router rewrite that touched 17 unrelated
endpoints, broken CORS configuration, and a `google-genai<2.0` pin that
conflicts with Module 4's `>=2.0` pin already used elsewhere). This issue
does not import anything from that branch. It pins `google-genai>=2.0` to
match Module 4's PR #48 instead, so as not to add a *third* conflicting
version constraint to an already-known cross-module dependency conflict.

## The layers, and why they're separate files

- `backend/app/analytics/insights/prompt.py` — turns a session summary into
  a prompt string. Pure function, no imports outside the standard library.
- `backend/app/analytics/insights/fallback.py` — builds the deterministic
  paragraph. Also pure, also no Gemini/network involvement at all.
- `backend/app/analytics/insights/validation.py` — checks a raw Gemini
  answer before it's trusted (non-empty, plausible length, no prohibited
  wording).
- `backend/app/analytics/insights/gemini_client.py` — the only file in
  Module 8 that imports the `google-genai` SDK, and even there the import
  is lazy (inside the function), so nothing about it can break test
  collection or force the package to be installed just to run unit tests.
- `backend/app/analytics/insights/generator.py` — ties the above together:
  try Gemini, validate, fall back if anything at all goes wrong. Takes an
  **injected** `call_gemini` function rather than calling the SDK directly,
  which is what makes it testable without ever touching the network.
- `backend/app/analytics/persistence/insight_reports.py` — stores the
  result, one document per session (a retry replaces the same document,
  it never creates a second one).

This mirrors the same layer separation the rest of Module 8 already uses
(events → domain metrics → session analytics → **insights** → API), so
Gemini never touches raw data directly and the deterministic parts stay
independently testable.

## What "fallback" actually means here

Gemini being unavailable is treated as a completely normal, expected
situation — not an error to alarm anyone about. Reasons it might not run
today: no `GEMINI_API_KEY` configured (the default in development), the
service is temporarily down, a request times out, or its answer doesn't
pass validation (too short, too long, or uses language this project
specifically avoids). In every one of these cases, the learner still gets a
real paragraph — just one built from arithmetic on the same numbers instead
of written by a model. The dashboard also never implies the *numeric*
analytics failed just because the *written* paragraph came from the
fallback — those are two independent parts of the response.

## Report status and retries

A report can be in one of four states, matching
`shared/contracts/analytics-report.schema.json`:

- `pending` — no attempt has been made yet (the state every session starts
  in, set by Issue #28's finalization).
- `generated` — Gemini succeeded and its answer passed validation.
- `fallback_generated` — the deterministic paragraph was used instead, for
  any of the reasons above.
- `failed` — reserved for the case where even the deterministic fallback
  itself could not be built. This should not happen for a valid session
  summary, but is handled explicitly (rather than left to crash the retry
  endpoint) so a caller always gets a real answer back, and can retry.

Retrying only ever does something when the current status is `pending`
(the first-ever attempt) or `failed` (an actual retry). A report that
already reached `generated` or `fallback_generated` is left completely
untouched — this matters because Gemini's free tier is limited to 20
requests/day/model, so nothing in Module 8 ever calls it more than once per
session per status transition.

## Privacy

Only the already-computed, aggregate session summary is ever sent to
Gemini: engagement percentages, intervention counts and effectiveness,
recovery rate, assistant-usage counts, critical-section engagement, and
data-quality flags. Nothing else is available to `prompt.py` in the first
place — it only receives the summary dict, so there is no code path by
which a webcam frame, a full chat transcript, a raw gaze coordinate, or a
learner's email address could reach Gemini even by mistake.

## Environment variables

Set in `backend/.env` (see `backend/.env.example`):

| Variable | Required | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | No | Left blank in development to avoid cost — an empty key routes straight to the deterministic fallback, which is a normal, working state, not an error. |
| `GEMINI_MODEL` | No | Defaults to `gemini-2.0-flash`. |
| `GEMINI_TIMEOUT_SECONDS` | No | Defaults to `20`. |

## Testing

`backend/tests/analytics/test_insights.py` — pure unit tests for the prompt
builder, the fallback builder, validation, and the generator's
try-Gemini-then-fallback orchestration. Every test injects a fake
`call_gemini` function; none of them import or configure the real
`google-genai` SDK, and none can reach the network.

`backend/tests/analytics/test_persistence.py` — round-trip and
retry-replaces-rather-than-duplicates tests for the new
`InsightReportRepository`, plus its index.

`backend/tests/analytics/test_api.py` — `InsightReportRetryEndpointTests`
was rewritten (the old version tested stub behavior that no longer exists)
to cover: first attempt from `pending`, Gemini-unavailable-falls-back,
retry-after-failure increments `retry_count` without duplicating, no-op on
an already-generated report, and the contract shape of a saved report. A
new `InsightReportRetrievalIntegrationTests` class confirms `GET
.../analytics` never calls Gemini itself and correctly reflects whatever
the retry endpoint already produced.

Command: `python -m pytest backend/tests/analytics/ -q`
Result: **156 passed** (full Module 8 analytics suite, including this
issue's new tests).

## Known limitations

- **No correlation between a report and the exact metric_version its
  summary was computed under**, beyond the summary lookup itself already
  being versioned. If metric definitions change later, an old report is not
  automatically invalidated — this mirrors the same open question already
  flagged for learning profiles (Issue #33) and is a contract-level decision
  for later, not something patched in silently here.
- **`model_version` is always `None` today.** `model_name` records which
  Gemini model was configured (e.g. `gemini-2.0-flash`); the SDK/model's own
  version string is not separately tracked. Low-value to add without a
  concrete need.
- **The word-count and prohibited-wording checks in `validation.py` are
  deliberately loose**, not a rigorous content classifier — they catch
  obviously broken or clearly unsafe responses, not every possible subtle
  issue with Gemini's phrasing. A human-reviewed prompt is the primary
  safeguard; validation is a second line of defense.
- **No API endpoint for reading a report's retry history in detail** beyond
  `retry_count`/`last_attempted_at` on the stored document — not asked for
  by this issue.

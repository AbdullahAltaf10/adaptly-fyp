# Multi-Signal Paragraph Fusion + Dwell-Revisit Re-Reading Proxy — Design

Status: approved in chat (2026-09-29), pending written-spec review.
Owner: sibtain2345 (Module 3/4 area).
Scope: Module 3 (engagement) + Module 4 (intervention) + Module 5 (assistant, no changes needed) frontend/backend.

Explicitly **out of scope** for this spec (see "Decomposition" at the end):
`furrow.py` changes, the true OneStop gaze-regression saccade classifier (G8),
Module 6 (CV-AI Integration Layer), and the cross-module "full pipeline"
integration audit. Each of those needs its own brainstorming pass.

## 1. Problem

Scope document (page 10, Module 4) requires "the active paragraph identified
through multi-signal dwell-time and gaze fusion" to be sent to Gemini for
simplification. Today `useDwell.js` implements exactly **one** signal
(IntersectionObserver visibility ratio) — good enough to know which paragraph
is *on screen*, not which one the learner is *actually reading*.

Separately, scope page 7 objective #2 ("train a gaze regression classifier to
detect re-reading patterns") is currently a stub (`rereading.py`, always
returns `pending`) because the literal ask — a CNN/SVM on the OneStop dataset,
watching gaze-X at sub-second resolution for regression saccades — is blocked
on two independent things already documented in that file's docstring: OneStop
is 1000Hz lab data (not webcam-comparable, despite what the scope document
claims), and detecting a saccade that lasts tens of milliseconds needs a
faster capture stream than the current 1fps engagement loop. Both blockers are
architectural, not something this spec removes.

What **is** buildable now, confirmed with the user (2026-09-29 brainstorming
session): a paragraph-level "did the learner go backward and re-dwell on a
paragraph they'd already left" proxy, built entirely from data the system
already has at 1fps. This is honestly weaker than the scope document's literal
ask and must be documented as a proxy, not the real classifier.

## 2. Four signals and their confidence model

| # | Signal | Source | Availability | Relative confidence |
|---|---|---|---|---|
| S1 | Visibility ratio | `useDwell.js` IntersectionObserver (existing, unchanged) | Always | Baseline: high when one chunk dominates, low when 2+ chunks have close ratios |
| S2 | Coarse gaze-quadrant | New: derived client-side from the raw MediaPipe landmarks already produced every `CAPTURE_INTERVAL_MS` (~1s) in `useEngagementCapture.js`'s `captureFrame()` — iris-landmark horizontal/vertical offset + head yaw/pitch, mapped to a coarse vertical band of the viewport | Whenever a face is detected | Low — same ~2-3cm-equivalent imprecision the scope document itself states for webcam gaze |
| S3 | WebGazer.js precise gaze point | New npm dependency (`webgazer`), produces an (x,y) viewport-pixel estimate per frame after calibration | Only after the learner completes (or the system falls back gracefully past) a calibration step | Highest available, but still capped at paragraph-level containment — never claims word/line precision (scope p.14's own stated limit) |
| S4 | Mouse/scroll position | `mousemove` + `scroll` listeners, paragraph bounding rects via `getBoundingClientRect()` | Whenever the learner uses a mouse/trackpad | Lowest — tie-breaker only |

**Fusion score** for each on-screen chunk `c`:

```
score(c) = Σ_i confidence_i × vote_i(c)
```

where `vote_i(c) ∈ [0,1]`:
- S1: the IntersectionObserver ratio directly.
- S2/S3: 1.0 if the estimated point/band falls inside `c`'s bounding rect, a
  falloff toward 0 for near-misses (proximity-based, not binary), 0 otherwise.
- S4: 1.0 if the mouse is within a small vertical band of `c` and idle (no
  movement for > 1.5s) or the last scroll left `c` centred in view, else 0.

`activeChunkId` = the chunk with the highest `score`, provided it clears a
minimum threshold `MIN_FUSION_SCORE = 0.15` (estimate, not measured — prevents
flapping to a low-confidence guess when nothing is clearly the target).
`activeChunkId` and an overall normalized `fusionConfidence` are both exposed.

Starting confidence weights (all estimates, tunable, documented as such in
code and in the numbers-cheatsheet once this ships):
`S1 = 0.5` (dynamic, scaled by how dominant the top visibility ratio is over
the runner-up), `S2 = 0.15`, `S3 = 0.30` once calibrated (`0` before/without
calibration), `S4 = 0.10`. S3 > S1 once calibrated because it is the only
signal that can disambiguate two chunks with identical visibility ratios; S1
still carries the largest weight overall because it is the only signal that
is always fully available.

**Non-regression guarantee (hard requirement):** if S2, S3, and S4 are all
unavailable (no face, WebGazer denied/uncalibrated, no mouse activity), the
formula reduces to S1 alone — byte-for-byte the same `activeChunkId` decision
`useDwell.js` produces today, **on the first tick of a session.** This is
enforced by a unit test that runs the fusion function with only S1 present
and diffs the result against the existing `useDwell` recompute logic on the
same fixture inputs.

**Amendment, 2026-10-03:** from the second tick on, the S1-only path now
also applies the same temporal hysteresis as the S2-S4 branch (persist the
previous `activeChunkId` within `HYSTERESIS_MARGIN`, rather than flipping
to a new top ratio on noise). Reason: WebGazer (S3) had been running
uncalibrated for every session since this spec shipped — `webgazerSignal.js`
never called the WebGazer method that actually feeds its regression model
training data, so `otherSignalsPresent` was frequently false in practice and
the "fallback" path was the common one a real learner hit, not a rare edge
case. Leaving it with zero flicker protection reproduced the exact
flips-between-paragraphs symptom this whole module exists to prevent. The
byte-for-byte guarantee above still holds for a session's very first fusion
tick (no previous chunk exists yet to persist); see
`fusionScoring.js`'s own module docstring and `fusionScoring.test.js`'s
hysteresis describe block for the current, authoritative behavior.

## 3. Where fusion lives

New hook `frontend/src/intervention/useDwellFusion.js`, composing:
- The existing `useDwell()` (unchanged) for S1 + the registration API
  (`register(chunkId, element)`) the content viewer already calls.
- A new pure function module `frontend/src/intervention/fusionScoring.js`
  exporting `computeActiveChunk(signals, chunkRects) -> { activeChunkId, fusionConfidence, breakdown }`,
  kept framework-free and independently unit-testable (mirrors the project's
  existing pattern of pure-function core + hook wrapper, e.g. `landmarks.js` /
  `useEngagementCapture.js`).
- A new `frontend/src/engagement/gazeQuadrant.js` — the S2 heuristic, a pure
  function `estimateGazeBand(landmarks) -> { band, confidence }`, called from
  inside `useEngagementCapture.js`'s existing `captureFrame()` (the raw
  landmarks are already there; this adds no new capture cycle).
- A new `frontend/src/engagement/webgazerSignal.js` wrapping the `webgazer`
  package behind the same shape as the other signals (lazy-loaded, so pages
  that never mount a study session never pay for the WebGazer bundle).
- A new `frontend/src/intervention/mouseSignal.js` for S4.

`useDwellFusion` returns the same shape `useDwell` does today
(`{ register, seconds, chunkId, activeChunkId }`) plus `fusionConfidence` and
`signalBreakdown` (for debugging/analytics, not shown to the learner — scope's
"no scores shown during an active session" rule still applies). `StudySession.jsx`
swaps its `useDwell()` call for `useDwellFusion()`; no other call site changes,
because the returned shape is a superset.

## 4. Re-reading (paragraph-revisit proxy)

Backend `rereading.py` stops being a pure stub. New logic, still in the same
file:
- The engagement session already receives `chunk_id` on every `/analyze` call
  (existing field, wired since the earlier dwell chunk_id bug fix this
  session).
- Maintain a small per-session ordered history of `(chunk_order_index, ts)` —
  the content's chunk order is already known from Module 2's chunking, so
  "order index" is just position in that list.
- `detect_rereading` becomes: if the current chunk's order index is lower than
  the highest order index previously seen in this session, and the learner
  dwells on it again past `REVISIT_MIN_DWELL_SECONDS = 8` (estimate — long
  enough to rule out a scroll-past, short of a full read), mark
  `detected=True`, `status="available"`, populate `confidence` from how much
  lower the index is and how long the re-dwell lasts.
- Output feeds the **already-reserved** contract fields —
  `gaze_regression_detected` and Module 8's `reason_code=reading_difficulty` —
  so no schema change is needed anywhere, exactly as the current docstring
  anticipated.
- The docstring is rewritten to state plainly: this is a dwell-revisit
  heuristic, not the OneStop saccade classifier the scope document describes;
  that remains an open, documented gap (red-flags file, G8).

## 5. WebGazer calibration + font/line-spacing recommendation

New step in the existing pre-session flow (`usePreSessionCheck.js` /
`PreSessionCheck.jsx` pattern, same "warn, don't block" philosophy):

1. After camera + lighting checks pass, and only when the session has text
   content (skipped for video-only sessions), show a short calibration step:
   a handful of on-screen points the learner clicks, which is exactly how
   WebGazer's own interaction-based calibration works (its cited paper,
   scope ref [18], is literally "eye tracking using user interactions").
   Skippable at any time — skipping just means S3's confidence stays 0 for
   the whole session, same non-regression guarantee as above.
2. Immediately after calibration (or after skip, using only S1/S2/S4), show
   one short instruction sentence at the learner's **current** font/line-spacing
   settings for `READABILITY_PROBE_SECONDS = 8` (estimate), and read
   `fusionConfidence`/revisit signals during that window.
3. If the average `fusionConfidence` over the probe window is below
   `SCATTERED_CONFIDENCE_THRESHOLD = 0.3` (estimate) — i.e. the signals never
   settled on a clear "this is the paragraph being read" — surface a single
   dismissible suggestion, "Larger text might make this easier", offering
   exactly one step up in font size and/or line spacing,
   using the existing accessibility contract (`_SETTING_RULES`, already
   validated both frontend and backend). **Never auto-applies** — same
   principle as every other accessibility setting in this codebase, which is
   always learner-controlled.
4. This is explicitly documented (code comment + defense guide entry) as a
   heuristic UX nicety, not a validated readability instrument.

## 6. Module 4 / Module 5 integration

No contract changes. `chunk_id` already reaches the intervention service and
the assistant (wired earlier this session). Swapping `useDwell` for
`useDwellFusion` in `StudySession.jsx` is the only call-site change; downstream
consumers see a (hopefully) more accurate `activeChunkId`, nothing else.

## 7. Error handling

- WebGazer script fails to load / camera permission revoked mid-session: S3
  confidence drops to 0, no exception surfaces to the learner, fusion falls
  back to S1+S2+S4.
- No face detected for S2: that tick's S2 confidence is 0, same fallback.
- Fusion function called with zero signals available: returns
  `{ activeChunkId: null, fusionConfidence: 0 }`, matching `useDwell`'s
  existing "nothing is being read" null case.

## 8. Testing plan

- `fusionScoring.test.js` — pure function, synthetic signal fixtures,
  including the non-regression fixture (S1-only matches existing `useDwell`
  output).
- `gazeQuadrant.test.js` — synthetic landmark fixtures for band estimation.
- `useDwellFusion.test.jsx` — mirrors `useDwell.test.jsx`'s existing patterns.
- `webgazerSignal.test.js` — mocked `webgazer` module (calibration
  success/failure/skip paths).
- Backend `test_rereading.py` (new) — revisit sequences, confirms
  `gaze_regression_detected` populates correctly and that a purely-forward
  reading sequence never fires it.
- Every fix/behavior mutation-tested per this session's established practice.

## 9. Decomposition (why Module 6 and the full-pipeline audit are not in this spec)

The user's latest message asks for three things bundled together: (a) this
dwell-fusion feature, (b) Module 6 (CV-AI Integration Layer — a new subsystem
combining camera + chat + content signals every 60s, not designed at all
yet), and (c) a full audit/completion pass across every already-built module's
integration points. Per the brainstorming process, a request spanning
multiple independent subsystems gets decomposed rather than crammed into one
spec: (b) is a new subsystem and needs its own brainstorming session (data
flow, decision format, how it differs from this dwell-fusion work, storage);
(c) is a different kind of task entirely (verification/audit, not a new
feature) and does not belong in an architectural feature spec. Both are next
in queue after this spec ships, each getting their own design pass.

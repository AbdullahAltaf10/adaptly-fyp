# Multi-Signal Paragraph Fusion + Dwell-Revisit Re-Reading — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `useDwell`'s single visibility-only paragraph signal with a
four-signal confidence-weighted fusion (visibility, coarse gaze-quadrant,
WebGazer.js, mouse), add a paragraph-revisit re-reading proxy on the backend,
and add a pre-session WebGazer calibration + font/line-spacing suggestion
step — with a hard non-regression guarantee that the system behaves exactly
as it does today whenever the new signals are unavailable.

**Architecture:** A pure, framework-free scoring function
(`fusionScoring.js`) combines four independently-sourced signal readings into
one `activeChunkId` + `fusionConfidence`; a thin hook (`useDwellFusion`) wires
it to the DOM and to the existing `useDwell`/`useEngagementCapture` hooks
with no change to their existing contracts. On the backend, `rereading.py`
follows the exact same per-session-state pattern as `recovery.py`, and feeds
two already-reserved contract slots (`gaze_regression_detected`,
`REASON_READING_DIFFICULTY`) that exist today but are never populated.

**Tech Stack:** React 18 hooks, vitest/Testing Library (frontend); FastAPI,
pytest (backend); new npm dependency `webgazer`.

**Spec:** `docs/superpowers/specs/2026-09-29-dwell-fusion-rereading-design.md`

## Global Constraints

- `MIN_FUSION_SCORE = 0.15`, weights `S1(visibility)=0.5 dynamic / S2(gazeQuadrant)=0.15 / S3(webgazer)=0.30 / S4(mouse)=0.10`, `REVISIT_MIN_DWELL_SECONDS = 8`, `READABILITY_PROBE_SECONDS = 8`, `SCATTERED_CONFIDENCE_THRESHOLD = 0.3` — copied verbatim from the spec, all estimates, not measured.
- **Non-regression guarantee is a hard requirement**: when only the visibility signal is available, `computeActiveChunk` must return byte-identical `activeChunkId` decisions to `useDwell`'s existing `recompute()` on the same fixture inputs. This is a pinned test, not a suggestion.
- **No `shared/contracts/*.schema.json` changes anywhere in this plan.** `gaze_regression_detected` and `REASON_READING_DIFFICULTY` already exist in the wire contracts; this plan only starts populating them.
- Warn-don't-block posture everywhere a new capability can fail (WebGazer denied/unavailable, no face detected, calibration skipped): the feature degrades, it never blocks the session or throws to the learner.
- No score/confidence number is ever rendered to the learner during an active session (scope 6.8) — `fusionConfidence`/`signalBreakdown` are internal only.
- Every module boundary in `backend/app/engagement/` stays a closed set that knows nothing about `intervention` or `content` (per `session.py`'s own stated design) — `rereading.py` takes a plain `chunk_order: int | None`, it does not look up content chunks itself.
- Mutation-test every new behavior: after a step's test passes, briefly break the implementation on purpose and confirm the test catches it, then restore — this project's established practice for every change this session.
- **Do not run `git commit`.** Stage changes (`git add`) at the end of each task and stop there — per this project's standing rule, commits happen only when the user explicitly says the whole feature is done. Do not touch `backend/.venv`, `frontend/node_modules`, or `sibtain-workspace/.venv-ml`.

## Review Focus

- A chunk with zero registered DOM element (unregistered mid-fusion-tick, e.g. content re-rendered) — `computeActiveChunk` must skip it rather than throwing on a missing rect.
- WebGazer's script genuinely failing to load (blocked by an ad-blocker, offline CDN) — `calibrateWebgazer()` must resolve to `{ available: false }`, never reject uncaught into the pre-session UI.
- A learner with zero mouse/trackpad interaction for the whole session (touchscreen, keyboard-only navigation) — `useMouseSignal` must keep returning `null`/non-idle forever without ever reporting a false idle position at `(0,0)`.
- A session where the learner never leaves chunk 0 (short document, or re-reads immediately without ever progressing) — `rereading.update` must never report a false revisit when `chunk_order` has never decreased.
- Two chunks tied at the same visibility ratio with no other signal available — the non-regression path must resolve this exactly the way `useDwell`'s own `recompute()` does today: strict `>` comparison over `Map.forEach`'s insertion order means the FIRST chunk to reach the top ratio wins a tie, not the last, and it must never silently return `null` just because two chunks matched.

---

## File Structure

```
frontend/src/intervention/
  fusionScoring.js        NEW — pure 4-signal scoring function
  fusionScoring.test.js   NEW
  mouseSignal.js          NEW — S4
  mouseSignal.test.js     NEW
  useDwellFusion.js       NEW — composes useDwell + all 4 signals
  useDwellFusion.test.jsx NEW
  useDwell.js             MODIFY — add `visibilityRatios()` getter (additive)
  useDwell.test.jsx       MODIFY — one new test for the getter

frontend/src/engagement/
  gazeQuadrant.js             NEW — S2
  gazeQuadrant.test.js        NEW
  webgazerSignal.js           NEW — S3
  webgazerSignal.test.js      NEW
  useEngagementCapture.js     MODIFY — expose latest single-frame landmarks (additive)
  usePreSessionCheck.js       MODIFY — add calibration + readability-probe step state
  PreSessionCheck.jsx         MODIFY — render the new step
  PreSessionCheck.test.jsx    MODIFY — new tests for the new step

frontend/src/pages/
  StudySession.jsx          MODIFY — swap useDwell() for useDwellFusion(),
                             forward the landmarks getter, wire the font
                             suggestion callback

backend/app/engagement/
  rereading.py            REWRITE — real paragraph-revisit heuristic
  routes.py               MODIFY — AnalyzeRequest.chunk_order, wire rereading
  session.py               MODIFY — register rereading.reset in the rule set

backend/app/intervention/
  decider.py               MODIFY — Signals.paragraph_revisit_detected field
  policy.py                MODIFY — new independent decision branch
  service.py                MODIFY — thread the new signal through evaluate()

backend/tests/
  test_rereading.py                    NEW
  test_engagement_routes_rereading.py  NEW (chunk_order wiring)
  test_intervention_policy_rereading.py NEW
```

---

### Task 1: `fusionScoring.js` — pure scoring function

**Files:**
- Create: `frontend/src/intervention/fusionScoring.js`
- Test: `frontend/src/intervention/fusionScoring.test.js`

**Interfaces:**
- Produces: `computeActiveChunk(signals, chunkRects) -> { activeChunkId: string|null, fusionConfidence: number, breakdown: Record<string, number> }`, `MIN_FUSION_SCORE`, `SIGNAL_WEIGHTS` (both exported constants).
  - `signals: { visibility: Map<string, number>, gazeQuadrant: {band: "top"|"middle"|"bottom", confidence: number}|null, webgazer: {x: number, y: number, confidence: number}|null, mouse: {x: number, y: number, idle: boolean}|null }`
  - `chunkRects: Map<string, {top: number, bottom: number, left: number, right: number}>`

- [ ] **Step 1: Write the failing tests**

```javascript
// frontend/src/intervention/fusionScoring.test.js
import { describe, expect, it } from "vitest";
import { computeActiveChunk, MIN_FUSION_SCORE, SIGNAL_WEIGHTS } from "./fusionScoring";

function rect(top, bottom) {
  return { top, bottom, left: 0, right: 100 };
}

describe("computeActiveChunk: non-regression (visibility only)", () => {
  it("matches useDwell's own argmax when no other signal is present", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 0.3], ["b", 0.9]]);
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer: null, mouse: null }, chunkRects);
    expect(result.activeChunkId).toBe("b");
  });

  it("returns null when every ratio is zero, never a guess", () => {
    const chunkRects = new Map([["a", rect(0, 50)]]);
    const visibility = new Map([["a", 0]]);
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer: null, mouse: null }, chunkRects);
    expect(result.activeChunkId).toBeNull();
    expect(result.fusionConfidence).toBe(0);
  });

  it("picks a low but nonzero ratio even below MIN_FUSION_SCORE, matching useDwell", () => {
    // useDwell's own recompute() picks any ratio > 0 with no minimum floor.
    // The fused MIN_FUSION_SCORE gate must not regress that when no other
    // signal contributed anything.
    const chunkRects = new Map([["a", rect(0, 50)]]);
    const visibility = new Map([["a", 0.01]]);
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer: null, mouse: null }, chunkRects);
    expect(result.activeChunkId).toBe("a");
  });

  it("resolves a tie the same way useDwell's recompute() does: first chunk to reach the top ratio wins, never null", () => {
    // Map iteration is insertion order, and useDwell's own recompute() uses
    // strict `>`, so on a genuine tie "a" (inserted first) keeps the win
    // over "b" (inserted second, same ratio, does not exceed it).
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 0.5], ["b", 0.5]]);
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer: null, mouse: null }, chunkRects);
    expect(result.activeChunkId).toBe("a");
  });
});

describe("computeActiveChunk: fusion with additional signals", () => {
  it("lets a confident WebGazer point break a visibility tie", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 0.5], ["b", 0.5]]);
    const webgazer = { x: 10, y: 75, confidence: 1 }; // inside b's rect
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer, mouse: null }, chunkRects);
    expect(result.activeChunkId).toBe("b");
  });

  it("ignores a signal pointing at a chunk with no registered rect", () => {
    const chunkRects = new Map([["a", rect(0, 50)]]);
    const visibility = new Map([["a", 0.4]]);
    const webgazer = { x: 500, y: 500, confidence: 1 }; // far outside anything
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer, mouse: null }, chunkRects);
    expect(result.activeChunkId).toBe("a");
  });

  it("does not throw when chunkRects is empty", () => {
    const result = computeActiveChunk({ visibility: new Map(), gazeQuadrant: null, webgazer: null, mouse: null }, new Map());
    expect(result).toEqual({ activeChunkId: null, fusionConfidence: 0, breakdown: {} });
  });

  it("exposes the documented weights and threshold", () => {
    expect(MIN_FUSION_SCORE).toBe(0.15);
    expect(SIGNAL_WEIGHTS).toEqual({ visibility: 0.5, gazeQuadrant: 0.15, webgazer: 0.30, mouse: 0.10 });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/intervention/fusionScoring.test.js`
Expected: FAIL — `fusionScoring.js` does not exist yet.

- [ ] **Step 3: Write the implementation**

```javascript
// frontend/src/intervention/fusionScoring.js
/**
 * Combines four independently-sourced paragraph signals into one
 * activeChunkId + fusionConfidence. See
 * docs/superpowers/specs/2026-09-29-dwell-fusion-rereading-design.md
 * section 2 for where the weights and threshold come from.
 *
 * Non-regression is a hard requirement: when gazeQuadrant, webgazer, and
 * mouse are all absent, this must return exactly what useDwell's own
 * recompute() would - including picking a nonzero-but-tiny ratio, which
 * MIN_FUSION_SCORE would otherwise suppress. That case is handled as its
 * own path below rather than folded into the general formula.
 */

export const MIN_FUSION_SCORE = 0.15;

export const SIGNAL_WEIGHTS = {
  visibility: 0.5,
  gazeQuadrant: 0.15,
  webgazer: 0.30,
  mouse: 0.10,
};

const POINT_FALLOFF_PX = 80;
const BAND_HEIGHT_FRACTION = 1 / 3;

function pointVote(x, y, rect) {
  const inside = x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
  if (inside) return 1;
  const dx = x < rect.left ? rect.left - x : x > rect.right ? x - rect.right : 0;
  const dy = y < rect.top ? rect.top - y : y > rect.bottom ? y - rect.bottom : 0;
  const distance = Math.sqrt(dx * dx + dy * dy);
  return Math.max(0, 1 - distance / POINT_FALLOFF_PX);
}

function bandVote(band, rect, viewportHeight) {
  const bandIndex = { top: 0, middle: 1, bottom: 2 }[band];
  if (bandIndex === undefined) return 0;
  const bandTop = bandIndex * BAND_HEIGHT_FRACTION * viewportHeight;
  const bandBottom = bandTop + BAND_HEIGHT_FRACTION * viewportHeight;
  const overlap = Math.min(rect.bottom, bandBottom) - Math.max(rect.top, bandTop);
  const rectHeight = Math.max(1, rect.bottom - rect.top);
  return Math.max(0, Math.min(1, overlap / rectHeight));
}

/** The visibility-only path, identical to useDwell's own recompute(). */
function visibilityOnlyResult(visibility) {
  let bestId = null;
  let bestRatio = 0;
  visibility.forEach((ratio, chunkId) => {
    if (ratio > bestRatio) {
      bestRatio = ratio;
      bestId = chunkId;
    }
  });
  return {
    activeChunkId: bestRatio > 0 ? bestId : null,
    fusionConfidence: bestRatio > 0 ? SIGNAL_WEIGHTS.visibility : 0,
    breakdown: Object.fromEntries(visibility),
  };
}

export function computeActiveChunk(signals, chunkRects) {
  const visibility = signals.visibility ?? new Map();
  const otherSignalsPresent = Boolean(
    signals.gazeQuadrant || signals.webgazer || (signals.mouse && signals.mouse.idle)
  );

  if (chunkRects.size === 0) {
    return { activeChunkId: null, fusionConfidence: 0, breakdown: {} };
  }

  if (!otherSignalsPresent) {
    return visibilityOnlyResult(visibility);
  }

  const scores = new Map();
  for (const chunkId of chunkRects.keys()) scores.set(chunkId, 0);

  // S1: dominance-scaled visibility confidence.
  let topRatio = 0;
  let secondRatio = 0;
  visibility.forEach((ratio) => {
    if (ratio > topRatio) {
      secondRatio = topRatio;
      topRatio = ratio;
    } else if (ratio > secondRatio) {
      secondRatio = ratio;
    }
  });
  const dominance = topRatio > 0 ? Math.max(0, Math.min(1, (topRatio - secondRatio) / topRatio)) : 0;
  const visibilityConfidence = SIGNAL_WEIGHTS.visibility * (0.5 + 0.5 * dominance);
  visibility.forEach((ratio, chunkId) => {
    if (!scores.has(chunkId)) return; // chunk has no registered rect this tick
    scores.set(chunkId, scores.get(chunkId) + visibilityConfidence * ratio);
  });

  // S2: gaze-quadrant band.
  if (signals.gazeQuadrant) {
    const { band, confidence } = signals.gazeQuadrant;
    const viewportHeight = typeof window !== "undefined" ? window.innerHeight || 1 : 1;
    chunkRects.forEach((rect, chunkId) => {
      const vote = bandVote(band, rect, viewportHeight);
      if (vote > 0) scores.set(chunkId, scores.get(chunkId) + SIGNAL_WEIGHTS.gazeQuadrant * confidence * vote);
    });
  }

  // S3: WebGazer point.
  if (signals.webgazer) {
    const { x, y, confidence } = signals.webgazer;
    chunkRects.forEach((rect, chunkId) => {
      const vote = pointVote(x, y, rect);
      if (vote > 0) scores.set(chunkId, scores.get(chunkId) + SIGNAL_WEIGHTS.webgazer * confidence * vote);
    });
  }

  // S4: idle mouse position.
  if (signals.mouse && signals.mouse.idle) {
    const { x, y } = signals.mouse;
    chunkRects.forEach((rect, chunkId) => {
      const vote = pointVote(x, y, rect);
      if (vote > 0) scores.set(chunkId, scores.get(chunkId) + SIGNAL_WEIGHTS.mouse * vote);
    });
  }

  let bestId = null;
  let bestScore = 0;
  scores.forEach((score, chunkId) => {
    if (score > bestScore) {
      bestScore = score;
      bestId = chunkId;
    }
  });

  const breakdown = Object.fromEntries(scores);
  if (bestId === null || bestScore < MIN_FUSION_SCORE) {
    return { activeChunkId: null, fusionConfidence: 0, breakdown };
  }
  return { activeChunkId: bestId, fusionConfidence: Math.min(1, bestScore), breakdown };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/intervention/fusionScoring.test.js`
Expected: PASS, all 7 tests.

- [ ] **Step 5: Mutation check**

Temporarily change `if (!otherSignalsPresent)` to `if (false)` and re-run — the
"picks a low but nonzero ratio" test must fail (the general path's
`MIN_FUSION_SCORE` gate would suppress a 0.01 ratio). Restore the line.

- [ ] **Step 6: Stage for review**

```bash
git add frontend/src/intervention/fusionScoring.js frontend/src/intervention/fusionScoring.test.js
```

(Do not commit — see Global Constraints.)

---

### Task 2: `gazeQuadrant.js` — S2, coarse gaze-band heuristic

**Files:**
- Create: `frontend/src/engagement/gazeQuadrant.js`
- Test: `frontend/src/engagement/gazeQuadrant.test.js`

**Interfaces:**
- Consumes: raw landmarks in the `[[x, y, z], ...]` shape `toLandmarkArray` (in `frontend/src/engagement/landmarks.js`) already produces.
- Produces: `estimateGazeBand(landmarks) -> { band: "top"|"middle"|"bottom", confidence: number } | null`

- [ ] **Step 1: Write the failing tests**

```javascript
// frontend/src/engagement/gazeQuadrant.test.js
import { describe, expect, it } from "vitest";
import { estimateGazeBand } from "./gazeQuadrant";

const LEFT_EYE = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];
const LEFT_IRIS = [468, 469, 470, 471];
const RIGHT_IRIS = [473, 474, 475, 476];

/** Builds a 478-point landmark array with every point at (0.5, 0.5, 0), then
 * overrides the eye/iris groups so the mean iris y is `irisY` and the mean
 * eye y is 0.5 - reproducing the same averaging features.py itself does. */
function fixture(irisY) {
  const landmarks = Array.from({ length: 478 }, () => [0.5, 0.5, 0]);
  for (const index of [...LEFT_EYE, ...RIGHT_EYE]) landmarks[index] = [0.5, 0.5, 0];
  for (const index of [...LEFT_IRIS, ...RIGHT_IRIS]) landmarks[index] = [0.5, irisY, 0];
  return landmarks;
}

describe("estimateGazeBand", () => {
  it("returns null for a missing/too-short landmark array", () => {
    expect(estimateGazeBand(null)).toBeNull();
    expect(estimateGazeBand([[0, 0, 0]])).toBeNull();
  });

  it("reports 'top' when the iris sits above the measured population mean by more than one std dev", () => {
    // mean=-0.004969, std=0.001266 (scaler stats) -> top boundary is
    // 0.5 + (mean - std) since iris_y - eye_y should be very negative.
    const result = estimateGazeBand(fixture(0.5 - 0.01));
    expect(result.band).toBe("top");
  });

  it("reports 'bottom' when the iris sits below the mean by more than one std dev", () => {
    const result = estimateGazeBand(fixture(0.5 + 0.01));
    expect(result.band).toBe("bottom");
  });

  it("reports 'middle' at the population mean offset", () => {
    const result = estimateGazeBand(fixture(0.5 - 0.004969));
    expect(result.band).toBe("middle");
  });

  it("always reports the same fixed confidence, since its weight (not this value) encodes how coarse it is", () => {
    const result = estimateGazeBand(fixture(0.5));
    expect(result.confidence).toBe(1.0);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/engagement/gazeQuadrant.test.js`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```javascript
// frontend/src/engagement/gazeQuadrant.js
/**
 * A coarse, free "which vertical band of the viewport is the eye pointed
 * at" heuristic - the S2 fusion signal.
 *
 * Reuses the exact same iris-offset calculation ml/inference/features.py
 * uses for gaze_y (mean iris position minus mean eye position, per eye,
 * averaged) - not a new landmark formula, just computed here client-side,
 * once per capture tick, instead of waiting on a server round-trip.
 *
 * Deliberately coarse: the scope document states webcam gaze accuracy at
 * 2-3cm on screen, so this can only ever mean "roughly top/middle/bottom
 * third" - never a precise point. fusionScoring.js's low SIGNAL_WEIGHTS.gazeQuadrant
 * reflects that; this module's own confidence stays fixed at 1.0 because the
 * coarseness lives in the weight, not here.
 *
 * Thresholds are the trained scaler's own measured population mean/std for
 * gaze_y (ml/artifacts/MANIFEST.json, mirrored in
 * sibtain-workspace/FYP_DEFENSE_GUIDE/13_NUMBERS_CHEATSHEET.md) - reused so
 * the band boundaries mean something instead of being arbitrary numbers.
 */

const LEFT_EYE = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];
const LEFT_IRIS = [468, 469, 470, 471];
const RIGHT_IRIS = [473, 474, 475, 476];

const GAZE_Y_MEAN = -0.004969;
const GAZE_Y_STD = 0.001266;

const GAZE_QUADRANT_CONFIDENCE = 1.0;

function averagePoint(landmarks, indices) {
  let x = 0;
  let y = 0;
  for (const index of indices) {
    x += landmarks[index][0];
    y += landmarks[index][1];
  }
  return [x / indices.length, y / indices.length];
}

export function estimateGazeBand(landmarks) {
  if (!landmarks || landmarks.length <= Math.max(...RIGHT_IRIS)) return null;

  const leftIris = averagePoint(landmarks, LEFT_IRIS);
  const rightIris = averagePoint(landmarks, RIGHT_IRIS);
  const leftEye = averagePoint(landmarks, LEFT_EYE);
  const rightEye = averagePoint(landmarks, RIGHT_EYE);

  const gazeY = ((leftIris[1] - leftEye[1]) + (rightIris[1] - rightEye[1])) / 2;

  const band =
    gazeY < GAZE_Y_MEAN - GAZE_Y_STD ? "top" :
    gazeY > GAZE_Y_MEAN + GAZE_Y_STD ? "bottom" :
    "middle";

  return { band, confidence: GAZE_QUADRANT_CONFIDENCE };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/engagement/gazeQuadrant.test.js`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Mutation check**

Swap the `<` and `>` in the `band` ternary and confirm the "top"/"bottom"
tests fail; restore.

- [ ] **Step 6: Stage for review**

```bash
git add frontend/src/engagement/gazeQuadrant.js frontend/src/engagement/gazeQuadrant.test.js
```

---

### Task 3: `mouseSignal.js` — S4

**Files:**
- Create: `frontend/src/intervention/mouseSignal.js`
- Test: `frontend/src/intervention/mouseSignal.test.js`

**Interfaces:**
- Produces: `useMouseSignal({ enabled }) -> () => { x: number, y: number, idle: boolean } | null` (a hook returning a getter, same "read at fusion-tick time" pattern as `useDwell`'s `seconds`/`chunkId`).

- [ ] **Step 1: Write the failing tests**

```javascript
// frontend/src/intervention/mouseSignal.test.js
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useMouseSignal } from "./mouseSignal";

function moveMouseTo(x, y) {
  act(() => {
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: x, clientY: y }));
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useMouseSignal", () => {
  it("returns null before any mouse movement has ever been seen", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    expect(result.current()).toBeNull();
  });

  it("reports the last position as NOT idle immediately after moving", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(120, 240);
    expect(result.current()).toEqual({ x: 120, y: 240, idle: false });
  });

  it("reports idle=true once 1500ms pass with no further movement", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(50, 60);
    act(() => vi.advanceTimersByTime(1500));
    expect(result.current()).toEqual({ x: 50, y: 60, idle: true });
  });

  it("resets idle back to false on a fresh movement", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(10, 10);
    act(() => vi.advanceTimersByTime(1500));
    expect(result.current().idle).toBe(true);
    moveMouseTo(11, 11);
    expect(result.current().idle).toBe(false);
  });

  it("stops listening on unmount", () => {
    const { result, unmount } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(1, 1);
    unmount();
    moveMouseTo(2, 2); // must not throw, and has no observer left to update
    expect(result.current()).toEqual({ x: 1, y: 1, idle: false });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/intervention/mouseSignal.test.js`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```javascript
// frontend/src/intervention/mouseSignal.js
/**
 * Weakest fusion signal (S4): is the mouse idle near a paragraph. Mouse
 * position alone is a weak proxy for reading position - many readers never
 * move the mouse while reading - so fusionScoring.js gives it the lowest
 * weight and only uses it as a tie-breaker.
 */
import { useEffect, useRef } from "react";

const IDLE_MS = 1500;

export function useMouseSignal({ enabled = true } = {}) {
  const positionRef = useRef(null); // { x, y } | null
  const lastMoveRef = useRef(0);

  useEffect(() => {
    if (!enabled) return undefined;

    function onMove(event) {
      positionRef.current = { x: event.clientX, y: event.clientY };
      lastMoveRef.current = Date.now();
    }

    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, [enabled]);

  /** Read at fusion-tick time, not on every render. */
  return function getMouseSignal() {
    if (!positionRef.current) return null;
    const idle = Date.now() - lastMoveRef.current >= IDLE_MS;
    return { x: positionRef.current.x, y: positionRef.current.y, idle };
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/intervention/mouseSignal.test.js`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Mutation check**

Change `IDLE_MS` to `15000` temporarily and confirm the "reports idle=true"
test fails (1500ms advance is no longer enough); restore to `1500`.

- [ ] **Step 6: Stage for review**

```bash
git add frontend/src/intervention/mouseSignal.js frontend/src/intervention/mouseSignal.test.js
```

---

### Task 4: `webgazerSignal.js` — S3, WebGazer.js wrapper

**Files:**
- Create: `frontend/src/engagement/webgazerSignal.js`
- Test: `frontend/src/engagement/webgazerSignal.test.js`
- Modify: `frontend/package.json` (new dependency)

**Interfaces:**
- Produces: `calibrateWebgazer() -> Promise<{ available: boolean, reason?: string }>`, `getWebgazerSignal() -> { x: number, y: number, confidence: number } | null`, `stopWebgazer() -> void`.

- [ ] **Step 1: Install the dependency**

```bash
cd frontend && npm install webgazer
```

- [ ] **Step 2: Write the failing tests**

```javascript
// frontend/src/engagement/webgazerSignal.test.js
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let storedGazeListener = null;
let beginResult = Promise.resolve();
let endCalled = false;

const webgazerMock = {
  setRegression: vi.fn(() => webgazerMock),
  setGazeListener: vi.fn((callback) => {
    storedGazeListener = callback;
    return webgazerMock;
  }),
  showVideo: vi.fn(() => webgazerMock),
  showFaceOverlay: vi.fn(() => webgazerMock),
  showFaceFeedbackBox: vi.fn(() => webgazerMock),
  showPredictionPoints: vi.fn(() => webgazerMock),
  begin: vi.fn(() => beginResult),
  end: vi.fn(() => { endCalled = true; }),
};

vi.mock("webgazer", () => ({ default: webgazerMock }));

beforeEach(async () => {
  vi.resetModules();
  storedGazeListener = null;
  beginResult = Promise.resolve();
  endCalled = false;
});

describe("webgazerSignal", () => {
  it("reports unavailable before calibration has ever run", async () => {
    const { getWebgazerSignal } = await import("./webgazerSignal");
    expect(getWebgazerSignal()).toBeNull();
  });

  it("starts reporting gaze points once calibration resolves and the listener fires", async () => {
    const { calibrateWebgazer, getWebgazerSignal } = await import("./webgazerSignal");
    const result = await calibrateWebgazer();
    expect(result.available).toBe(true);
    storedGazeListener({ x: 640, y: 200 });
    expect(getWebgazerSignal()).toEqual({ x: 640, y: 200, confidence: 1.0 });
  });

  it("ignores a null gaze event without throwing", async () => {
    const { calibrateWebgazer, getWebgazerSignal } = await import("./webgazerSignal");
    await calibrateWebgazer();
    storedGazeListener(null);
    expect(getWebgazerSignal()).toBeNull();
  });

  it("resolves available:false, never rejects, when begin() throws", async () => {
    beginResult = Promise.reject(new Error("camera permission denied"));
    const { calibrateWebgazer, getWebgazerSignal } = await import("./webgazerSignal");
    const result = await calibrateWebgazer();
    expect(result).toEqual({ available: false, reason: "camera permission denied" });
    expect(getWebgazerSignal()).toBeNull();
  });

  it("stopWebgazer clears the last known prediction and calls webgazer.end()", async () => {
    const { calibrateWebgazer, getWebgazerSignal, stopWebgazer } = await import("./webgazerSignal");
    await calibrateWebgazer();
    storedGazeListener({ x: 1, y: 1 });
    stopWebgazer();
    await Promise.resolve(); // let the .then() in stopWebgazer run
    expect(getWebgazerSignal()).toBeNull();
    expect(endCalled).toBe(true);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/engagement/webgazerSignal.test.js`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Write the implementation**

```javascript
// frontend/src/engagement/webgazerSignal.js
/**
 * Wraps the `webgazer` package behind the same shape as the other fusion
 * signals, and lazy-loads it - a study page that never runs a session never
 * pays for the WebGazer bundle.
 *
 * WebGazer calibrates itself from click interactions (Papoutsaki et al.,
 * scope ref [18]) - its estimate is only trustworthy after calibrateWebgazer()
 * resolves `available: true`. Before that, or if the browser/camera refuses
 * it, this reports null and fusion falls back to the other three signals -
 * same warn-don't-block posture as every other pre-session check in this
 * codebase.
 */

let webgazerModulePromise = null;
let latestPrediction = null;

function loadWebgazer() {
  if (!webgazerModulePromise) {
    webgazerModulePromise = import("webgazer").then((module) => module.default ?? module);
  }
  return webgazerModulePromise;
}

export async function calibrateWebgazer() {
  try {
    const webgazer = await loadWebgazer();
    webgazer.setGazeListener((data) => {
      latestPrediction = data ? { x: data.x, y: data.y } : null;
    });
    webgazer
      .showVideo(false)
      .showFaceOverlay(false)
      .showFaceFeedbackBox(false)
      .showPredictionPoints(false);
    await webgazer.setRegression("ridge").begin();
    return { available: true };
  } catch (error) {
    latestPrediction = null;
    return { available: false, reason: error.message };
  }
}

const WEBGAZER_CONFIDENCE = 1.0;

/** Reads WebGazer's latest gaze estimate, or null before calibration / this tick. */
export function getWebgazerSignal() {
  if (!latestPrediction) return null;
  return { x: latestPrediction.x, y: latestPrediction.y, confidence: WEBGAZER_CONFIDENCE };
}

export function stopWebgazer() {
  latestPrediction = null;
  if (!webgazerModulePromise) return;
  webgazerModulePromise.then((webgazer) => webgazer.end()).catch(() => {});
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/engagement/webgazerSignal.test.js`
Expected: PASS, all 5 tests.

- [ ] **Step 6: Mutation check**

Remove the `try`/`catch` around the `begin()` call temporarily (let it throw
uncaught) and confirm the "resolves available:false" test fails; restore.

- [ ] **Step 7: Stage for review**

```bash
git add frontend/src/engagement/webgazerSignal.js frontend/src/engagement/webgazerSignal.test.js frontend/package.json frontend/package-lock.json
```

---

### Task 5: `useDwell.js` additive getter + `useDwellFusion.js`

**Files:**
- Modify: `frontend/src/intervention/useDwell.js` (add one line to the return object; no other change)
- Modify: `frontend/src/intervention/useDwell.test.jsx` (one new test)
- Create: `frontend/src/intervention/useDwellFusion.js`
- Test: `frontend/src/intervention/useDwellFusion.test.jsx`

**Interfaces:**
- Consumes: `useDwell()` (existing), `computeActiveChunk` (Task 1), `estimateGazeBand` (Task 2), `useMouseSignal` (Task 3), `getWebgazerSignal` (Task 4).
- Produces: `useDwellFusion({ enabled, getLatestLandmarks }) -> { register(chunkId, element), seconds(), chunkId(), activeChunkId, fusionConfidence }` — a strict superset of `useDwell`'s return shape, so any existing caller can swap hooks with no other change.

- [ ] **Step 1: Add the additive getter to `useDwell.js`**

In `frontend/src/intervention/useDwell.js`, add one export to the returned
object (no other line changes):

```javascript
  /** Read-only snapshot of every registered chunk's current visibility ratio. */
  const visibilityRatios = useCallback(() => new Map(ratiosRef.current), []);

  return { register, seconds, chunkId, activeChunkId, visibilityRatios };
```

- [ ] **Step 2: Write the failing test for the getter**

Add to `frontend/src/intervention/useDwell.test.jsx`:

```javascript
  it("exposes a read-only snapshot of every chunk's visibility ratio", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    const first = document.createElement("section");
    const second = document.createElement("section");
    act(() => {
      result.current.register("0", first);
      result.current.register("1", second);
    });
    see(first, 0.3);
    see(second, 0.9);
    expect(result.current.visibilityRatios()).toEqual(new Map([["0", 0.3], ["1", 0.9]]));
  });
```

- [ ] **Step 3: Run to verify the new test fails, then implement, then pass**

Run: `cd frontend && npx vitest run src/intervention/useDwell.test.jsx`
Expected: FAIL first (`visibilityRatios is not a function`), then apply Step 1's
change and re-run for PASS (all tests, old and new).

- [ ] **Step 4: Write the failing tests for `useDwellFusion`**

```javascript
// frontend/src/intervention/useDwellFusion.test.jsx
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDwellFusion } from "./useDwellFusion";

let observers = [];
class FakeIntersectionObserver {
  constructor(callback) { this.callback = callback; this.targets = new Set(); observers.push(this); }
  observe(target) { this.targets.add(target); }
  unobserve(target) { this.targets.delete(target); }
  disconnect() { this.targets.clear(); }
}
function see(element, ratio) {
  act(() => observers.forEach((o) => o.callback([{ target: element, intersectionRatio: ratio }])));
}

beforeEach(() => {
  observers = [];
  vi.useFakeTimers();
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useDwellFusion", () => {
  it("behaves exactly like useDwell when no extra signals are ever available", () => {
    const { result } = renderHook(() => useDwellFusion({ enabled: true }));
    const el = document.createElement("section");
    Object.defineProperty(el, "getBoundingClientRect", {
      value: () => ({ top: 0, bottom: 100, left: 0, right: 100 }),
    });
    act(() => result.current.register("0", el));
    see(el, 0.8);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBe("0");
    expect(result.current.chunkId()).toBe("0");
  });

  it("reports fusionConfidence 0 and null when nothing is registered", () => {
    const { result } = renderHook(() => useDwellFusion({ enabled: true }));
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBeNull();
    expect(result.current.fusionConfidence).toBe(0);
  });

  it("passes the getLatestLandmarks() result through to the gaze-quadrant signal without throwing when it returns null", () => {
    const getLatestLandmarks = vi.fn(() => null);
    const { result } = renderHook(() => useDwellFusion({ enabled: true, getLatestLandmarks }));
    const el = document.createElement("section");
    Object.defineProperty(el, "getBoundingClientRect", { value: () => ({ top: 0, bottom: 100, left: 0, right: 100 }) });
    act(() => result.current.register("0", el));
    see(el, 0.5);
    act(() => vi.advanceTimersByTime(1000));
    expect(getLatestLandmarks).toHaveBeenCalled();
    expect(result.current.activeChunkId).toBe("0");
  });
});
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/intervention/useDwellFusion.test.jsx`
Expected: FAIL — module does not exist.

- [ ] **Step 6: Write the implementation**

```javascript
// frontend/src/intervention/useDwellFusion.js
/**
 * Superset of useDwell(): everything it already does (visibility-based
 * chunkId/activeChunkId/seconds/register), plus the S2/S3/S4 signals folded
 * in through fusionScoring's non-regression-guaranteed formula. Any existing
 * caller of useDwell() can swap to this hook with no other change -
 * see StudySession.jsx.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useDwell } from "./useDwell";
import { computeActiveChunk } from "./fusionScoring";
import { useMouseSignal } from "./mouseSignal";
import { estimateGazeBand } from "../engagement/gazeQuadrant";
import { getWebgazerSignal } from "../engagement/webgazerSignal";

const FUSION_INTERVAL_MS = 1000;

export function useDwellFusion({ enabled = true, getLatestLandmarks } = {}) {
  const dwell = useDwell({ enabled });
  const getMouseSignal = useMouseSignal({ enabled });

  const elementsRef = useRef(new Map()); // chunkId -> element
  const [fusionResult, setFusionResult] = useState({ activeChunkId: null, fusionConfidence: 0 });

  const register = useCallback((chunkId, element) => {
    dwell.register(chunkId, element);
    if (!element) {
      elementsRef.current.delete(chunkId);
      return;
    }
    elementsRef.current.set(chunkId, element);
  }, [dwell]);

  useEffect(() => {
    if (!enabled) return undefined;

    const timer = setInterval(() => {
      const chunkRects = new Map();
      elementsRef.current.forEach((element, chunkId) => {
        chunkRects.set(chunkId, element.getBoundingClientRect());
      });

      const gazeQuadrant = getLatestLandmarks ? estimateGazeBand(getLatestLandmarks()) : null;
      const webgazer = getWebgazerSignal();
      const mouse = getMouseSignal();

      setFusionResult(
        computeActiveChunk(
          { visibility: dwell.visibilityRatios(), gazeQuadrant, webgazer, mouse },
          chunkRects
        )
      );
    }, FUSION_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [enabled, dwell, getLatestLandmarks, getMouseSignal]);

  const activeChunkId = fusionResult.activeChunkId;
  const chunkId = useCallback(() => activeChunkId ?? dwell.chunkId(), [activeChunkId, dwell]);

  return {
    register,
    seconds: dwell.seconds,
    chunkId,
    activeChunkId,
    fusionConfidence: fusionResult.fusionConfidence,
  };
}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/intervention/useDwellFusion.test.jsx`
Expected: PASS, all 3 tests.

- [ ] **Step 8: Mutation check**

Temporarily hardcode `chunkRects` to always be `new Map()` inside the
interval callback and confirm the first test (non-regression) fails; restore.

- [ ] **Step 9: Stage for review**

```bash
git add frontend/src/intervention/useDwell.js frontend/src/intervention/useDwell.test.jsx frontend/src/intervention/useDwellFusion.js frontend/src/intervention/useDwellFusion.test.jsx
```

---

### Task 6: Wire `useDwellFusion` into `StudySession.jsx`

**Files:**
- Modify: `frontend/src/pages/StudySession.jsx`
- Modify: `frontend/src/engagement/useEngagementCapture.js` (additive: expose latest single-frame landmarks)
- Test: `frontend/src/pages/StudySession.chunkWiring.test.jsx` (existing file — extend)

**Interfaces:**
- Consumes: `useDwellFusion` (Task 5).
- Produces: `useEngagementCapture(...)` gains one new returned field, `getLatestLandmarks: () => (Array|null)`, read at fusion-tick time (same "getter, not state" pattern already used for `getDwellSeconds`/`getChunkId`).

This task is slightly more than a one-line hook swap: `useDwellFusion` needs
raw per-tick landmarks for the S2 signal, and today only
`useEngagementCapture`'s internal `captureFrame()` ever sees them.

- [ ] **Step 1: Expose the latest landmarks from `useEngagementCapture`**

In `frontend/src/engagement/useEngagementCapture.js`, inside `captureFrame()`,
after the existing `const results = landmarkerRef.current.detectForVideo(...)`
line, store the flattened result:

```javascript
      const landmarks = toLandmarkArray(results);
      latestLandmarksRef.current = landmarks;
      windowRef.current.push(landmarks);
```

(replacing the current `windowRef.current.push(toLandmarkArray(results));`
line so the value is computed once and reused). Add
`const latestLandmarksRef = useRef(null);` near the other refs at the top of
the hook, and add to the hook's returned object:

```javascript
    getLatestLandmarks: () => latestLandmarksRef.current,
```

- [ ] **Step 2: Write the failing test**

Add to `frontend/src/engagement/useEngagementCapture.test.jsx` (existing
test file for this hook — follow its existing mocking setup for
`createFaceLandmarker`/`getUserMedia` already present there):

```javascript
  it("exposes the most recent frame's landmarks via getLatestLandmarks()", async () => {
    // Reuses this file's existing harness: mocked landmarker returns a fixed
    // detectForVideo() result, camera/getUserMedia mocked, capture interval
    // advanced by CAPTURE_INTERVAL_MS to trigger one captureFrame() tick.
    const { result } = renderCapture(); // existing helper in this file
    await act(async () => { vi.advanceTimersByTime(CAPTURE_INTERVAL_MS); });
    expect(result.current.getLatestLandmarks()).not.toBeNull();
    expect(Array.isArray(result.current.getLatestLandmarks())).toBe(true);
  });
```

- [ ] **Step 3: Run, implement, run**

Run: `cd frontend && npx vitest run src/engagement/useEngagementCapture.test.jsx`
Expected: FAIL, then apply Step 1, then PASS (this new test plus every
existing test in the file, unchanged).

- [ ] **Step 4: Swap the hook in `StudySession.jsx`**

In `frontend/src/pages/StudySession.jsx`, find the existing `useDwell(...)`
call and the `useEngagementCapture(...)` call. Replace:

```javascript
  const dwell = useDwell({ enabled: sessionActive });
```

with:

```javascript
  const dwell = useDwellFusion({
    enabled: sessionActive,
    getLatestLandmarks: capture.getLatestLandmarks,
  });
```

(`capture` is the existing variable already holding the
`useEngagementCapture(...)` result in this file — only the import line
`import { useDwell } from "../intervention/useDwell";` becomes
`import { useDwellFusion } from "../intervention/useDwellFusion";`, and every
other reference to `dwell.register`/`dwell.seconds`/`dwell.chunkId`/
`dwell.activeChunkId` already in this file stays exactly as it is, since
`useDwellFusion`'s return shape is a superset.)

- [ ] **Step 5: Run the existing chunk-wiring test to confirm no regression**

Run: `cd frontend && npx vitest run src/pages/StudySession.chunkWiring.test.jsx`
Expected: PASS, unchanged — this file already asserts the assistant receives
the correct active chunk; it must keep passing with no edits to its own
assertions, since `useDwellFusion`'s default (no other signals wired up in
this test's fixtures) behaves exactly like `useDwell`.

- [ ] **Step 6: Stage for review**

```bash
git add frontend/src/pages/StudySession.jsx frontend/src/engagement/useEngagementCapture.js frontend/src/engagement/useEngagementCapture.test.jsx
```

---

### Task 7: Pre-session WebGazer calibration + readability-probe suggestion

**Files:**
- Modify: `frontend/src/engagement/usePreSessionCheck.js`
- Modify: `frontend/src/engagement/PreSessionCheck.jsx`
- Modify: `frontend/src/engagement/PreSessionCheck.test.jsx`

**Interfaces:**
- Consumes: `calibrateWebgazer`, `stopWebgazer` (Task 4).
- Produces: `usePreSessionCheck(...)` gains `webgazerStatus: "idle"|"calibrating"|"ready"|"unavailable"`, `startWebgazerCalibration()`, `skipWebgazerCalibration()`, `readabilitySuggestion: {fontUp: boolean, lineSpacingUp: boolean} | null`, `dismissReadabilitySuggestion()`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/engagement/PreSessionCheck.test.jsx` (existing file —
follow its existing `check` prop-fixture pattern):

```javascript
  it("shows a skippable 'calibrate your eyes' step once the camera is ready", () => {
    const check = baseCheck({ cameraReady: true, webgazerStatus: "idle" });
    render(<PreSessionCheck check={check} onStart={() => {}} />);
    expect(screen.getByText(/calibrate/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /skip/i })).toBeInTheDocument();
  });

  it("does not block Start while calibration is unavailable", () => {
    const check = baseCheck({ cameraReady: true, webgazerStatus: "unavailable" });
    render(<PreSessionCheck check={check} onStart={() => {}} />);
    expect(screen.getByRole("button", { name: /start session/i })).not.toBeDisabled();
  });

  it("shows a dismissible font/line-spacing suggestion when one is present", () => {
    const check = baseCheck({
      cameraReady: true,
      webgazerStatus: "ready",
      readabilitySuggestion: { fontUp: true, lineSpacingUp: false },
      dismissReadabilitySuggestion: vi.fn(),
    });
    render(<PreSessionCheck check={check} onStart={() => {}} />);
    expect(screen.getByText(/larger text might make this easier/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(check.dismissReadabilitySuggestion).toHaveBeenCalled();
  });

  it("never renders a suggestion when readabilitySuggestion is null", () => {
    const check = baseCheck({ cameraReady: true, webgazerStatus: "ready", readabilitySuggestion: null });
    render(<PreSessionCheck check={check} onStart={() => {}} />);
    expect(screen.queryByText(/larger text/i)).not.toBeInTheDocument();
  });
```

(`baseCheck(overrides)` is a small local helper this test file should define
once at the top, merging `overrides` onto the same minimal `check` object
shape the file's existing tests already construct by hand — camera/lowLight/
checking/recheck/videoRef fields plus the new ones above.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/engagement/PreSessionCheck.test.jsx`
Expected: FAIL — new UI does not exist yet.

- [ ] **Step 3: Add calibration + readability-probe state to `usePreSessionCheck.js`**

Add alongside the existing state in `usePreSessionCheck`:

```javascript
import { calibrateWebgazer, stopWebgazer } from "./webgazerSignal";

const READABILITY_PROBE_SECONDS = 8;
const SCATTERED_CONFIDENCE_THRESHOLD = 0.3;

// ...inside usePreSessionCheck(...), alongside the existing useState calls:
  const [webgazerStatus, setWebgazerStatus] = useState("idle");
  const [readabilitySuggestion, setReadabilitySuggestion] = useState(null);
  const confidenceSamplesRef = useRef([]);

  const startWebgazerCalibration = useCallback(async () => {
    setWebgazerStatus("calibrating");
    const result = await calibrateWebgazer();
    setWebgazerStatus(result.available ? "ready" : "unavailable");
  }, []);

  const skipWebgazerCalibration = useCallback(() => {
    setWebgazerStatus("unavailable");
  }, []);

  /**
   * Called by the study page once per fusion tick during the readability
   * probe window, with the current fusionConfidence. After
   * READABILITY_PROBE_SECONDS samples, a low average suggests a suggestion.
   */
  const recordReadabilitySample = useCallback((confidence) => {
    confidenceSamplesRef.current.push(confidence);
    if (confidenceSamplesRef.current.length < READABILITY_PROBE_SECONDS) return;
    const average =
      confidenceSamplesRef.current.reduce((a, b) => a + b, 0) / confidenceSamplesRef.current.length;
    if (average < SCATTERED_CONFIDENCE_THRESHOLD) {
      setReadabilitySuggestion({ fontUp: true, lineSpacingUp: true });
    }
    confidenceSamplesRef.current = [];
  }, []);

  const dismissReadabilitySuggestion = useCallback(() => setReadabilitySuggestion(null), []);

  useEffect(() => () => stopWebgazer(), []);
```

Add `webgazerStatus, startWebgazerCalibration, skipWebgazerCalibration,
readabilitySuggestion, recordReadabilitySample, dismissReadabilitySuggestion`
to the hook's returned object.

- [ ] **Step 4: Render the new step in `PreSessionCheck.jsx`**

Add, immediately after the existing lighting `<Row>` block, gated the same
way the lighting row already is (only once `check.cameraReady`):

```jsx
        {check.cameraReady && check.webgazerStatus !== "unavailable" && (
          <div className="rounded-md border border-line bg-page p-3 mb-3">
            <p className="m-0 mb-2 text-sm text-ink">
              Optional: calibrate eye tracking for better paragraph focus.
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                onClick={check.startWebgazerCalibration}
                disabled={check.webgazerStatus === "calibrating" || check.webgazerStatus === "ready"}
              >
                {check.webgazerStatus === "ready" ? "Calibrated" : "Calibrate"}
              </Button>
              <Button variant="secondary" onClick={check.skipWebgazerCalibration}>
                Skip
              </Button>
            </div>
          </div>
        )}

        {check.readabilitySuggestion && (
          <div role="status" className="flex items-start justify-between gap-2 rounded-md border border-line bg-page p-3 mb-3 text-sm">
            <span>Larger text might make this easier to follow.</span>
            <Button variant="secondary" onClick={check.dismissReadabilitySuggestion}>
              Dismiss
            </Button>
          </div>
        )}
```

`canStart` is unchanged — it already only depends on `cameraReady`,
`documentLoading`, `documentError` (per section 3 of the spec: calibration
never blocks Start).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/engagement/PreSessionCheck.test.jsx`
Expected: PASS, all tests (new and existing).

- [ ] **Step 6: Mutation check**

Temporarily make `canStart` also require `check.webgazerStatus === "ready"`
and confirm the "does not block Start while calibration is unavailable" test
fails; restore.

- [ ] **Step 7: Stage for review**

```bash
git add frontend/src/engagement/usePreSessionCheck.js frontend/src/engagement/PreSessionCheck.jsx frontend/src/engagement/PreSessionCheck.test.jsx
```

---

### Task 8: Backend — `rereading.py` real paragraph-revisit heuristic

**Files:**
- Rewrite: `backend/app/engagement/rereading.py`
- Test: `backend/tests/test_rereading.py`

**Interfaces:**
- Produces: `update(uid: str, session_id: str, chunk_order: int | None, dwell_seconds: float) -> dict` returning `{"status": "available", "detected": bool, "confidence": float|None, "reason": str}`; `reset(uid: str, session_id: str) -> None`; `is_available() -> bool` (now returns `True`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_rereading.py
from app.engagement import rereading


def teardown_function(_fn):
    rereading.reset("u1", "s1")


def test_is_available_now_returns_true():
    assert rereading.is_available() is True


def test_no_revisit_on_purely_forward_reading():
    for order in [0, 1, 2, 3]:
        result = rereading.update("u1", "s1", order, dwell_seconds=10.0)
    assert result["status"] == "available"
    assert result["detected"] is False


def test_detects_a_revisit_to_an_earlier_chunk_with_enough_dwell():
    rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    rereading.update("u1", "s1", 1, dwell_seconds=10.0)
    rereading.update("u1", "s1", 2, dwell_seconds=10.0)
    result = rereading.update("u1", "s1", 0, dwell_seconds=9.0)  # >= REVISIT_MIN_DWELL_SECONDS=8
    assert result["detected"] is True
    assert result["confidence"] is not None and result["confidence"] > 0


def test_does_not_detect_a_revisit_below_the_minimum_dwell():
    rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    rereading.update("u1", "s1", 2, dwell_seconds=10.0)
    result = rereading.update("u1", "s1", 0, dwell_seconds=3.0)  # below REVISIT_MIN_DWELL_SECONDS
    assert result["detected"] is False


def test_a_chunk_never_counts_as_a_revisit_of_itself():
    rereading.update("u1", "s1", 2, dwell_seconds=5.0)
    result = rereading.update("u1", "s1", 2, dwell_seconds=20.0)
    assert result["detected"] is False


def test_none_order_never_crashes_and_is_never_a_revisit():
    result = rereading.update("u1", "s1", None, dwell_seconds=20.0)
    assert result["detected"] is False


def test_sessions_are_independent():
    rereading.update("u1", "s1", 5, dwell_seconds=10.0)
    result = rereading.update("u1", "s2", 0, dwell_seconds=10.0)
    assert result["detected"] is False


def test_reset_clears_history_so_the_next_session_starts_clean():
    rereading.update("u1", "s1", 3, dwell_seconds=10.0)
    rereading.reset("u1", "s1")
    result = rereading.update("u1", "s1", 0, dwell_seconds=10.0)
    assert result["detected"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_rereading.py -v`
Expected: FAIL — current stub always returns `status="pending"`,
`detected=False`, and takes a different signature (`detect_rereading(gaze_x_series)`).

- [ ] **Step 3: Rewrite `rereading.py`**

```python
"""
Paragraph-revisit re-reading proxy.

STATUS: implemented as a heuristic, NOT the classifier scope section 6.3
describes. That classifier - a CNN/SVM trained on the OneStop Eye Movements
dataset, watching gaze-X at sub-second resolution for a regression saccade -
remains an open, documented gap (see
sibtain-workspace/FYP_DEFENSE_GUIDE/11_RED_FLAGS_AND_HONEST_LIMITS.md, G8) for
two independent, architectural reasons: OneStop is 1000Hz lab-grade data, not
webcam-comparable, and a saccade lasts tens of milliseconds against this
pipeline's 1fps sampling rate. Neither is solved here.

What IS implemented: using data the engagement loop already has at 1fps -
which chunk the learner is on, and for how long - to detect a coarser,
paragraph-level pattern: did the learner go BACK to a paragraph they had
already moved past, and stay there long enough for it to be a real re-read
rather than a scroll-past. This is honestly weaker evidence than a real
saccade classifier, and is documented as such everywhere it is used.

Design mirrors recovery.py exactly: per-(uid, session_id) history, evicted on
a TTL, and an explicit reset() called from session.py on session start/end -
the same closed rule-module pattern every other file in this package follows.
This module knows nothing about content or intervention; it takes a plain
`chunk_order` integer and leaves looking that up to whoever calls it
(engagement/routes.py), keeping the module boundary session.py's own
docstring describes.
"""

import time

SESSION_TTL_SECONDS = 1800

# How long a re-dwell on an earlier chunk must last before it counts as a
# real re-read rather than a scroll-past glance. Estimate, not measured -
# DAiSEE has no dwell signal, same caveat as Module 4's own dwell gates.
REVISIT_MIN_DWELL_SECONDS = 8

# (uid, session_id) -> {"max_order_seen": int, "last_seen": float}
_sessions = {}


def _evict_stale(now: float) -> None:
    stale = [key for key, s in _sessions.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for key in stale:
        del _sessions[key]


def is_available() -> bool:
    """Whether re-reading detection can produce a real answer. Now: yes -
    as the dwell-revisit proxy described above, not the OneStop classifier."""
    return True


def update(uid: str, session_id: str, chunk_order, dwell_seconds: float) -> dict:
    """
    chunk_order: this window's chunk's position in the content's reading
    order (0-based), or None when the caller has none to report - a
    camera-only session, or a chunk the content lookup could not resolve.
    dwell_seconds: how long the learner has been on this chunk (same value
    Module 4's policy already receives).
    """
    now = time.time()
    _evict_stale(now)

    key = (uid, session_id)
    session = _sessions.setdefault(key, {"max_order_seen": None, "last_seen": now})
    session["last_seen"] = now

    if chunk_order is None:
        return {
            "status": "available",
            "detected": False,
            "confidence": None,
            "reason": "No chunk order reported for this window.",
        }

    max_seen = session["max_order_seen"]
    is_revisit = (
        max_seen is not None
        and chunk_order < max_seen
        and dwell_seconds >= REVISIT_MIN_DWELL_SECONDS
    )

    if max_seen is None or chunk_order > max_seen:
        session["max_order_seen"] = chunk_order

    if is_revisit:
        # How far back, relative to how far the learner had progressed -
        # going back to paragraph 0 after reaching paragraph 10 is stronger
        # evidence than going back one paragraph out of two.
        distance = max_seen - chunk_order
        confidence = min(1.0, distance / max(1, max_seen))
        return {
            "status": "available",
            "detected": True,
            "confidence": round(confidence, 3),
            "reason": (
                f"Returned to paragraph {chunk_order} after reaching "
                f"{max_seen}, and stayed {dwell_seconds:.0f}s."
            ),
        }

    return {
        "status": "available",
        "detected": False,
        "confidence": None,
        "reason": "No qualifying revisit this window.",
    }


def reset(uid: str, session_id: str) -> None:
    """Drop a session's revisit history (session end, or after recalibration)."""
    _sessions.pop((uid, session_id), None)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_rereading.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Mutation check**

Temporarily change `chunk_order < max_seen` to `chunk_order <= max_seen` and
confirm `test_a_chunk_never_counts_as_a_revisit_of_itself` fails; restore.

- [ ] **Step 6: Stage for review**

```bash
git add backend/app/engagement/rereading.py backend/tests/test_rereading.py
```

---

### Task 9: Backend wiring — routes, session reset, and the intervention policy

**Files:**
- Modify: `backend/app/engagement/routes.py`
- Modify: `backend/app/engagement/session.py`
- Modify: `backend/app/intervention/decider.py`
- Modify: `backend/app/intervention/policy.py`
- Modify: `backend/app/intervention/service.py`
- Test: `backend/tests/test_engagement_routes_rereading.py` (new)
- Test: `backend/tests/test_intervention_policy_rereading.py` (new)

This is where the two already-reserved contract slots
(`gaze_regression_detected`, `REASON_READING_DIFFICULTY`) actually start
getting populated. Frontend's `chunk_order` is additive on the existing
`AnalyzeRequest` model — the same category of change as `dwell_seconds`
before the content viewer existed, not a `shared/contracts/*.schema.json`
change.

**Interfaces:**
- `AnalyzeRequest` gains `chunk_order: Optional[int] = None`.
- `Signals` (decider.py) gains `paragraph_revisit_detected: bool = False`.
- `evaluate(...)` (service.py) gains `paragraph_revisit_detected: bool = False`, threaded straight into `Signals(...)`.

- [ ] **Step 1: Register `rereading` in `session.py`'s rule-reset set**

```python
from app.engagement import deep_thinking, fatigue, furrow, recovery, rereading, smoothing
```

and change:

```python
    for module in (smoothing, fatigue, recovery, deep_thinking, furrow):
```

to:

```python
    for module in (smoothing, fatigue, recovery, deep_thinking, furrow, rereading):
```

- [ ] **Step 2: Add `chunk_order` to `AnalyzeRequest` and wire the real call in routes.py**

In `AnalyzeRequest`:

```python
    chunk_order: Optional[int] = None
```

Replace:

```python
            gaze_regression_detected=False,   # never measured; see rereading.py
```

with:

```python
            gaze_regression_detected=rereading_result["detected"],
```

adding, just before `event = contracts.build_engagement_event(...)`:

```python
        rereading_result = rereading.update(
            uid, session_id, payload.chunk_order, payload.dwell_seconds or 0.0
        )
```

and replace the diagnostics line:

```python
                "rereading": rereading.detect_rereading([]),
```

with:

```python
                "rereading": rereading_result,
```

and pass the signal into the intervention call, adding one argument to the
existing `intervention.evaluate(...)` call:

```python
                paragraph_revisit_detected=rereading_result["detected"],
```

- [ ] **Step 3: Write the failing routes test**

```python
# backend/tests/test_engagement_routes_rereading.py
"""
Confirms chunk_order flows end-to-end: /analyze populates
gaze_regression_detected on a genuine revisit, and never on forward-only
reading. Follows this suite's existing pattern for hitting /engagement/analyze
with a fake authenticated user and WINDOW_SIZE synthetic frames - see
test_engagement_routes.py in this same directory for the fixture this reuses.
"""
from tests.test_engagement_routes import VALID_FRAMES, auth_headers, client  # existing fixtures


def _analyze(session_id, chunk_order, dwell_seconds):
    return client.post(
        "/engagement/analyze",
        json={
            "frames": VALID_FRAMES,
            "session_id": session_id,
            "chunk_id": str(chunk_order),
            "chunk_order": chunk_order,
            "dwell_seconds": dwell_seconds,
        },
        headers=auth_headers(),
    )


def test_forward_reading_never_sets_gaze_regression_detected():
    session_id = "rereading-route-forward"
    for order in [0, 1, 2]:
        response = _analyze(session_id, order, dwell_seconds=10.0)
    assert response.json()["event"]["gaze_regression_detected"] is False


def test_a_qualifying_revisit_sets_gaze_regression_detected():
    session_id = "rereading-route-revisit"
    _analyze(session_id, 0, dwell_seconds=10.0)
    _analyze(session_id, 1, dwell_seconds=10.0)
    response = _analyze(session_id, 0, dwell_seconds=9.0)
    assert response.json()["event"]["gaze_regression_detected"] is True
```

(If `test_engagement_routes.py`'s existing `VALID_FRAMES`/`auth_headers`/`client`
fixtures are named or shaped differently, use this file's own actual names —
they already exist and are exercised by that file's current tests for the
same `/analyze` endpoint.)

- [ ] **Step 4: Run to verify it fails, apply Steps 1-2, run to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_engagement_routes_rereading.py -v`
Expected: FAIL (chunk_order not yet accepted / gaze_regression_detected always
False), then PASS after Steps 1-2.

- [ ] **Step 5: Add `paragraph_revisit_detected` to `Signals` (decider.py)**

At the end of the `Signals` dataclass's field list (after
`discouraged_types: frozenset = frozenset()`):

```python
    # Set by the paragraph-revisit re-reading proxy (engagement/rereading.py).
    # Independent of the LSTM's raw_struggling/brow_struggling path - see
    # policy.py for how it is used as its own, separate trigger.
    paragraph_revisit_detected: bool = False
```

- [ ] **Step 6: Import `REASON_READING_DIFFICULTY` and add the policy branch**

In `policy.py`, add `REASON_READING_DIFFICULTY` to the existing import from
`app.intervention.decider`:

```python
from app.intervention.decider import (
    ASSISTANT_HELP_PROMPT,
    BREAK_SUGGESTION,
    BULLET_SUMMARY,
    REASON_FATIGUE,
    REASON_READING_DIFFICULTY,
    REASON_STRUGGLING,
    SIMPLIFY_CONTENT,
    TIER_BROAD,
    TIER_RULE,
    TIER_STRONG,
    Decision,
    Signals,
)
```

Replace:

```python
        strong = signals.raw_struggling and signals.brow_struggling
        broad = signals.raw_struggling or signals.brow_struggling
        if not broad:
            return None
```

with:

```python
        strong = signals.raw_struggling and signals.brow_struggling
        broad = signals.raw_struggling or signals.brow_struggling
        if not broad:
            # Independent of the engagement model entirely - the scope
            # document itself frames re-reading detection this way ("a
            # separate binary classifier ... independent of the engagement
            # model"). This is the proxy version of that independence: a
            # learner can trigger this with zero struggling/brow evidence.
            if (
                signals.paragraph_revisit_detected
                and ASSISTANT_HELP_PROMPT not in signals.discouraged_types
            ):
                return Decision(
                    intervention_type=ASSISTANT_HELP_PROMPT,
                    reason_code=REASON_READING_DIFFICULTY,
                    reason="Went back to an earlier paragraph and stayed there — offered the assistant.",
                    tier=TIER_BROAD,
                    chunk_id=signals.chunk_id,
                    content_id=signals.content_id,
                    triggering_engagement_event_id=signals.engagement_event_id,
                )
            return None
```

- [ ] **Step 7: Thread the signal through `service.py`'s `evaluate()`**

Add one parameter to `evaluate(...)`:

```python
    paragraph_revisit_detected: bool = False,
```

and one field to its `Signals(...)` construction:

```python
        paragraph_revisit_detected=paragraph_revisit_detected,
```

- [ ] **Step 8: Write the failing policy test**

```python
# backend/tests/test_intervention_policy_rereading.py
from app.intervention.decider import ASSISTANT_HELP_PROMPT, REASON_READING_DIFFICULTY, Signals
from app.intervention.policy import DefaultPolicy


def _signals(**overrides):
    base = dict(
        state="focused",
        source="lstm",
        confidence=0.9,
        raw_struggling=False,
        brow_struggling=False,
        dwell_seconds=0.0,
    )
    base.update(overrides)
    return Signals(**base)


def test_revisit_alone_triggers_the_assistant_prompt_with_reading_difficulty_reason():
    policy = DefaultPolicy()
    decision = policy.decide(_signals(paragraph_revisit_detected=True))
    assert decision is not None
    assert decision.intervention_type == ASSISTANT_HELP_PROMPT
    assert decision.reason_code == REASON_READING_DIFFICULTY


def test_no_revisit_and_no_struggling_triggers_nothing():
    policy = DefaultPolicy()
    decision = policy.decide(_signals(paragraph_revisit_detected=False))
    assert decision is None


def test_struggling_evidence_still_wins_over_a_simultaneous_revisit():
    # The existing struggling path is checked first in this branch's parent
    # `if not broad` guard - a revisit alongside real struggling evidence
    # must not downgrade an already-earned stronger response.
    policy = DefaultPolicy()
    decision = policy.decide(
        _signals(raw_struggling=True, brow_struggling=True, dwell_seconds=999, paragraph_revisit_detected=True)
    )
    assert decision.reason_code != REASON_READING_DIFFICULTY


def test_discouraged_assistant_prompt_suppresses_the_revisit_trigger():
    policy = DefaultPolicy()
    decision = policy.decide(
        _signals(paragraph_revisit_detected=True, discouraged_types=frozenset({ASSISTANT_HELP_PROMPT}))
    )
    assert decision is None
```

- [ ] **Step 9: Run to verify it fails, apply Steps 5-7, run to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_intervention_policy_rereading.py -v`
Expected: FAIL (`Signals` has no such field yet), then PASS after Steps 5-7.

- [ ] **Step 10: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS — every previously-passing test (819 before this plan) still
passes, plus the new ones from this task and Task 8.

- [ ] **Step 11: Mutation check**

Temporarily delete the `if (not broad)` branch's new `if
signals.paragraph_revisit_detected...` block entirely (restore the bare
`return None`) and confirm `test_revisit_alone_triggers_the_assistant_prompt...`
fails; restore.

- [ ] **Step 12: Stage for review**

```bash
git add backend/app/engagement/routes.py backend/app/engagement/session.py backend/app/intervention/decider.py backend/app/intervention/policy.py backend/app/intervention/service.py backend/tests/test_engagement_routes_rereading.py backend/tests/test_intervention_policy_rereading.py
```

---

## Final full-suite check

- [ ] **Backend:** `cd backend && .venv/Scripts/python.exe -m pytest -q` — expect all prior tests plus this plan's new tests passing, 0 failures.
- [ ] **Frontend:** `cd frontend && npx vitest run` — expect all prior tests plus this plan's new tests passing, 0 failures.
- [ ] **Frontend build:** `cd frontend && npm run build` — expect a clean build (WebGazer is dynamically imported per Task 4, so it must not bloat the main bundle — worth eyeballing the build output's chunk sizes).

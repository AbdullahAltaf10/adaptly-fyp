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

  it("falls back to the visibility-only pick when an unhelpful extra signal would otherwise push the fused score below MIN_FUSION_SCORE", () => {
    // A paragraph only 20% visible would still be picked with no other
    // signal (visibilityOnlyResult has no minimum floor - see the
    // non-regression tests above). An idle mouse sitting somewhere
    // irrelevant (a sidebar, say) contributes nothing useful, but its mere
    // presence must not turn an otherwise-clear pick into a shrug.
    const chunkRects = new Map([["a", rect(0, 50)]]);
    const visibility = new Map([["a", 0.2]]);
    const mouse = { x: 900, y: 900, idle: true }; // far from "a", contributes ~0
    const result = computeActiveChunk({ visibility, gazeQuadrant: null, webgazer: null, mouse }, chunkRects);
    expect(result.activeChunkId).toBe("a");
  });
});

describe("computeActiveChunk: temporal hysteresis (avoids flicker on a real tie)", () => {
  // Grounded in the confidence-weighted multimodal fusion literature's
  // "avoid flicker via temporal persistence" pattern (a disagreeing extra
  // signal should not arbitrarily reassign an ambiguous tie to whichever
  // chunk happens to iterate first - it should stay with whichever chunk
  // was already the answer, the same way a Kalman-filtered gaze estimate
  // stays put rather than jittering between equally-plausible readings).
  it("keeps the previously active chunk on an exact tie, instead of first-in-map-wins", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 1], ["b", 1]]); // both fully visible, no visibility lead
    const gazeQuadrant = { band: "top", confidence: 1 }; // agrees with neither rect
    const result = computeActiveChunk(
      { visibility, gazeQuadrant, webgazer: null, mouse: null },
      chunkRects,
      "b" // previously active
    );
    expect(result.activeChunkId).toBe("b");
  });

  it("keeps the previously active chunk within a small margin, not only on an exact tie", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 1], ["b", 0.97]]); // "a" nudges ahead, but barely
    const gazeQuadrant = { band: "top", confidence: 1 }; // agrees with neither - just enters the fused branch
    const result = computeActiveChunk(
      { visibility, gazeQuadrant, webgazer: null, mouse: null },
      chunkRects,
      "b"
    );
    expect(result.activeChunkId).toBe("b");
  });

  it("still switches once the new chunk's lead clearly exceeds the hysteresis margin", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const webgazer = { x: 10, y: 25, confidence: 1 }; // squarely inside a's rect
    const visibility = new Map([["a", 1], ["b", 1]]);
    const result = computeActiveChunk(
      { visibility, gazeQuadrant: null, webgazer, mouse: null },
      chunkRects,
      "b"
    );
    expect(result.activeChunkId).toBe("a");
  });

  it("has no previous chunk to persist on the very first tick", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 1], ["b", 1]]);
    const result = computeActiveChunk(
      { visibility, gazeQuadrant: null, webgazer: null, mouse: null },
      chunkRects,
      null
    );
    expect(result.activeChunkId).toBe("a"); // ordinary first-reaches-top-score behavior
  });

  it("ignores a previous chunk id that no longer has a registered rect", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 1], ["b", 1]]);
    const gazeQuadrant = { band: "top", confidence: 1 };
    const result = computeActiveChunk(
      { visibility, gazeQuadrant, webgazer: null, mouse: null },
      chunkRects,
      "c" // scrolled away and unregistered
    );
    expect(result.activeChunkId).toBe("a");
  });

  it("applies hysteresis on the pure-visibility path too, not only when extra signals are present", () => {
    // 2026-10-03 reversal of a prior deliberate decision: the additional
    // signals (WebGazer, gaze-quadrant, mouse) are frequently absent in a
    // real session - WebGazer in particular was never actually trained
    // until addMouseEventListeners() was wired up (webgazerSignal.js) - so
    // the pure-visibility path is the COMMON case in practice, not a rare
    // fallback, and leaving it with zero flicker protection reproduced the
    // exact "settles on neither paragraph, flips between them" symptom this
    // module exists to prevent. The exact-tie non-regression test above
    // still holds with no previous chunk (first tick); this only changes
    // behavior once there IS a previous chunk to persist.
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 0.5], ["b", 0.5]]);
    const result = computeActiveChunk(
      { visibility, gazeQuadrant: null, webgazer: null, mouse: null },
      chunkRects,
      "b"
    );
    expect(result.activeChunkId).toBe("b"); // stays put on the tie, does not flip to "a"
  });

  it("keeps the previous chunk on the pure-visibility path within the hysteresis margin, not only on an exact tie", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 0.55], ["b", 0.52]]); // "a" nudges ahead, but barely
    const result = computeActiveChunk(
      { visibility, gazeQuadrant: null, webgazer: null, mouse: null },
      chunkRects,
      "b"
    );
    expect(result.activeChunkId).toBe("b");
  });

  it("still switches on the pure-visibility path once the lead clearly exceeds the hysteresis margin", () => {
    const chunkRects = new Map([["a", rect(0, 50)], ["b", rect(50, 100)]]);
    const visibility = new Map([["a", 0.9], ["b", 0.1]]);
    const result = computeActiveChunk(
      { visibility, gazeQuadrant: null, webgazer: null, mouse: null },
      chunkRects,
      "b"
    );
    expect(result.activeChunkId).toBe("a");
  });
});

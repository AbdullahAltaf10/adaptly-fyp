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
 *
 * Temporal hysteresis (2026-09-30): a real webcam observed live could
 * produce a genuine, sustained tie - e.g. two short paragraphs both fully
 * visible at once, with a coarse gaze-band signal that doesn't clearly
 * favour either. Without persistence, that tie was broken by Map
 * iteration order (whichever chunk was registered first), which could
 * flip mid-tie for no reason a learner would ever notice a cause for.
 * Confidence-weighted multimodal fusion research consistently uses
 * temporal persistence to avoid exactly this flicker (see e.g. PMC
 * 13119640's "soft suppression" gating and the general "confidence-trend
 * -driven dynamic weighting" pattern) - the same principle a Kalman-
 * filtered gaze estimate uses to stay put on an ambiguous reading rather
 * than jittering between equally-plausible ones. Scoped to the
 * additional-signals branch only: the pure-visibility path's
 * non-regression contract with useDwell's own exact-tie behavior is a
 * separate, deliberate guarantee and must not change.
 */

export const MIN_FUSION_SCORE = 0.15;

// How much of a score lead a new chunk needs before it is allowed to
// displace the chunk that was already active. Kept well below a single
// signal's own weight (the smallest, mouse, is 0.10) so hysteresis damps
// noise-level ties without ever overriding a genuinely confident switch.
const HYSTERESIS_MARGIN = 0.05;

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

export function computeActiveChunk(signals, chunkRects, previousActiveChunkId = null) {
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

  // Hysteresis: a new chunk only displaces the one that was already active
  // if its lead is clear. A tie or near-tie stays with the previous answer
  // instead of flipping on noise (see the module docstring).
  if (
    previousActiveChunkId !== null
    && previousActiveChunkId !== bestId
    && scores.has(previousActiveChunkId)
    && scores.get(previousActiveChunkId) >= bestScore - HYSTERESIS_MARGIN
  ) {
    bestId = previousActiveChunkId;
    bestScore = scores.get(previousActiveChunkId);
  }

  const breakdown = Object.fromEntries(scores);
  if (bestId === null || bestScore < MIN_FUSION_SCORE) {
    // The extra signals contributed nothing decisive - fall back to what
    // visibility alone would have picked, rather than discarding an
    // otherwise-clear read just because S2-S4 happened to be present and
    // unhelpful. A low-but-nonzero visibility ratio would have been picked
    // with no other signal at all (see the non-regression tests); an
    // unhelpful extra signal must not make that worse.
    const fallback = visibilityOnlyResult(visibility);
    return { ...fallback, breakdown };
  }
  return { activeChunkId: bestId, fusionConfidence: Math.min(1, bestScore), breakdown };
}

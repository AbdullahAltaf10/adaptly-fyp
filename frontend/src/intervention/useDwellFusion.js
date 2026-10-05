// frontend/src/intervention/useDwellFusion.js
/**
 * Superset of useDwell(): everything it already does (visibility-based
 * chunkId/activeChunkId/seconds/register), plus the S2/S3/S4 signals folded
 * in through fusionScoring's non-regression-guaranteed formula. Any existing
 * caller of useDwell() can swap to this hook with no other change -
 * see StudySession.jsx.
 *
 * The visibility-only path is recomputed on every render, not gated behind
 * the polling interval below: useDwell's own activeChunkId already changes
 * react state synchronously (see its switchTo()), so waiting up to 1s to
 * reflect that here would itself be a regression against the hook this
 * replaces. Only gazeQuadrant/webgazer/mouse are polled - they are plain
 * function reads with no render of their own to piggyback on.
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
  const previousFusedChunkIdRef = useRef(null);
  const [polled, setPolled] = useState({ gazeQuadrant: null, webgazer: null, mouse: null });

  // Depends on dwell.register specifically, not the whole `dwell` object:
  // useDwell returns a fresh object literal every render, so depending on it
  // directly would give this callback a new identity every render too - and
  // since ContentChunk's own ref callback is memoized on [onChunkRef, ...]
  // (see content/ContentViewer.jsx), a changing identity here forces React
  // to unregister and re-register every chunk on every single render,
  // resetting accumulated dwell continuously. dwell.register itself is
  // already stable (useDwell memoizes it independently of the wrapper).
  const register = useCallback((chunkId, element) => {
    dwell.register(chunkId, element);
    if (!element) {
      elementsRef.current.delete(chunkId);
      return;
    }
    elementsRef.current.set(chunkId, element);
  }, [dwell.register]);

  useEffect(() => {
    if (!enabled) return undefined;

    const timer = setInterval(() => {
      setPolled({
        gazeQuadrant: getLatestLandmarks ? estimateGazeBand(getLatestLandmarks()) : null,
        webgazer: getWebgazerSignal(),
        mouse: getMouseSignal(),
      });
    }, FUSION_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [enabled, getLatestLandmarks, getMouseSignal]);

  const chunkRects = new Map();
  elementsRef.current.forEach((element, chunkId) => {
    chunkRects.set(chunkId, element.getBoundingClientRect());
  });

  // Hysteresis needs last tick's FUSED answer specifically (not
  // dwell.activeChunkId, which is the separate visibility-only pick) - see
  // fusionScoring.js's module docstring for why a tie must persist rather
  // than flip on noise.
  const fusionResult = computeActiveChunk(
    { visibility: dwell.visibilityRatios(), ...polled },
    chunkRects,
    previousFusedChunkIdRef.current
  );
  previousFusedChunkIdRef.current = fusionResult.activeChunkId;

  const activeChunkId = fusionResult.activeChunkId;
  const chunkId = useCallback(() => activeChunkId ?? dwell.chunkId(), [activeChunkId, dwell.chunkId]);

  // dwell.seconds() alone tracks useDwell's OWN internal decision
  // (visibility only), which the fused activeChunkId can override to a
  // different chunk (a confident WebGazer point breaking a visibility tie,
  // say). Reporting dwell.seconds() unmodified in that case would describe
  // how long the WRONG chunk has been visible, not how long the fused
  // answer has actually been the answer - review finding 6. In the common
  // case, where fusion agrees with dwell's own pick, this defers to
  // dwell.seconds() exactly, inheriting its hidden-tab accounting for free;
  // only the rarer override case gets its own, simpler timer.
  const overrideRef = useRef(null); // { chunkId, since, accumulated } | null
  if (activeChunkId !== dwell.activeChunkId) {
    if (overrideRef.current?.chunkId !== activeChunkId) {
      overrideRef.current = activeChunkId
        ? { chunkId: activeChunkId, since: Date.now(), accumulated: 0 }
        : null;
    }
  } else {
    overrideRef.current = null;
  }

  const seconds = useCallback(() => {
    const override = overrideRef.current;
    if (override) {
      return override.accumulated + (Date.now() - override.since) / 1000;
    }
    return dwell.seconds();
  }, [dwell]);

  return {
    register,
    seconds,
    chunkId,
    activeChunkId,
    fusionConfidence: fusionResult.fusionConfidence,
  };
}

/**
 * How long the learner has been on the chunk they are actually reading.
 *
 * This was written as a seam before there was anything to watch: nothing
 * registered, `chunkId` stayed null, `seconds()` returned 0, and the two
 * dwell-gated interventions could never fire however long someone stared at a
 * hard paragraph. `ContentViewer` closes that (issue #47) by calling
 * `register(chunk_id, element)` for every chunk it renders — and it did so
 * with no change to this file, the capture loop, or the backend, which is what
 * the seam was for.
 *
 * Two decisions that belong to Module 4 rather than to the viewer, which is
 * why they live here and not there:
 *
 * **Dwell is the most visible chunk, not any visible chunk.** A paragraph
 * halfway out of the viewport is not being read.
 *
 * **A hidden tab does not accumulate dwell.** Somebody who switched away is
 * not struggling with the paragraph, and counting that time would push them
 * over a threshold that is supposed to mean sustained effort.
 *
 * `seconds()` is a function rather than state on purpose. The capture loop
 * reads it once a second; returning it as state would re-render the study
 * page every second and restart the capture effect.
 */

import { useCallback, useEffect, useRef } from "react";

const VISIBILITY_THRESHOLDS = [0, 0.25, 0.5, 0.75, 1];

export function useDwell({ enabled = true } = {}) {
  const observerRef = useRef(null);
  const ratiosRef = useRef(new Map()); // chunkId -> visible ratio
  const elementsRef = useRef(new Map()); // element -> chunkId
  const activeRef = useRef(null); // { chunkId, since, accumulated }

  const switchTo = useCallback((chunkId) => {
    const now = Date.now();
    const active = activeRef.current;
    if (active?.chunkId === chunkId) return;
    activeRef.current = chunkId ? { chunkId, since: now, accumulated: 0 } : null;
  }, []);

  const recompute = useCallback(() => {
    let best = null;
    let bestRatio = 0;
    ratiosRef.current.forEach((ratio, chunkId) => {
      if (ratio > bestRatio) {
        bestRatio = ratio;
        best = chunkId;
      }
    });
    switchTo(bestRatio > 0 ? best : null);
  }, [switchTo]);

  useEffect(() => {
    if (!enabled || typeof IntersectionObserver === "undefined") return undefined;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const chunkId = elementsRef.current.get(entry.target);
          if (chunkId != null) {
            ratiosRef.current.set(chunkId, entry.intersectionRatio);
          }
        });
        recompute();
      },
      { threshold: VISIBILITY_THRESHOLDS }
    );

    function onVisibilityChange() {
      const active = activeRef.current;
      if (!active) return;
      if (document.visibilityState === "hidden") {
        // Bank what has been earned and stop the clock.
        active.accumulated += (Date.now() - active.since) / 1000;
        active.since = null;
      } else if (active.since === null) {
        active.since = Date.now();
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      observerRef.current?.disconnect();
      observerRef.current = null;
      ratiosRef.current.clear();
      elementsRef.current.clear();
      activeRef.current = null;
    };
  }, [enabled, recompute]);

  /**
   * Called by the content viewer for each chunk element it renders.
   * Passing a null element unregisters, so it works as a React ref callback:
   *
   *     <p ref={(el) => register(chunk.chunk_id, el)}>
   */
  const register = useCallback((chunkId, element) => {
    const observer = observerRef.current;
    if (!element) {
      elementsRef.current.forEach((id, el) => {
        if (id === chunkId) {
          observer?.unobserve(el);
          elementsRef.current.delete(el);
        }
      });
      ratiosRef.current.delete(chunkId);
      recompute();
      return;
    }
    elementsRef.current.set(element, chunkId);
    observer?.observe(element);
  }, [recompute]);

  /** Seconds on the current chunk. 0 when nothing is being read. */
  const seconds = useCallback(() => {
    const active = activeRef.current;
    if (!active) return 0;
    const running = active.since === null ? 0 : (Date.now() - active.since) / 1000;
    return active.accumulated + running;
  }, []);

  /** Which chunk the learner is on, for the analyze request. */
  const chunkId = useCallback(() => activeRef.current?.chunkId ?? null, []);

  return { register, seconds, chunkId };
}

/**
 * Turns the raw "is a face visible right now" flag into something worth
 * showing a learner.
 *
 * Reported directly it flickers: MediaPipe misses the occasional frame even
 * when nobody has moved, and an overlay that appears and vanishes several
 * times a minute is worse than no overlay. So a loss is only reported after a
 * grace period, and a return triggers a brief confirmation.
 */

import { useEffect, useRef, useState } from "react";

import { FACE_LOST_GRACE_MS, RECALIBRATE_SUGGEST_MS } from "./constants";

/** Must outlast the tick animation (circle 0.9s, then check 0.6s at 0.8s). */
const TICK_VISIBLE_MS = 2600;

export function useFacePresence({ faceDetected, enabled, calibrated }) {
  const lostRef = useRef(false);
  const lostAtRef = useRef(null);

  const [faceLost, setFaceLost] = useState(false);
  const [showTick, setShowTick] = useState(false);
  const [suggestRecalibrate, setSuggestRecalibrate] = useState(false);

  useEffect(() => {
    if (!enabled) return undefined;
    let timer;

    if (!faceDetected) {
      timer = setTimeout(() => {
        lostRef.current = true;
        lostAtRef.current = Date.now();
        setFaceLost(true);
      }, FACE_LOST_GRACE_MS);
    } else if (lostRef.current) {
      const awayMs = Date.now() - (lostAtRef.current ?? Date.now());
      lostRef.current = false;
      lostAtRef.current = null;
      setFaceLost(false);
      setShowTick(true);

      // A long absence usually means the learner got up or changed seat, which
      // makes the baseline stale. Offer a recalibration rather than silently
      // running one: an automatic baseline can quietly absorb real
      // disengagement by treating it as the new normal.
      if (awayMs >= RECALIBRATE_SUGGEST_MS && calibrated) {
        setSuggestRecalibrate(true);
      }
      timer = setTimeout(() => setShowTick(false), TICK_VISIBLE_MS);
    }

    return () => clearTimeout(timer);
  }, [faceDetected, enabled, calibrated]);

  return {
    faceLost,
    showTick,
    suggestRecalibrate,
    dismissRecalibrate: () => setSuggestRecalibrate(false),
  };
}

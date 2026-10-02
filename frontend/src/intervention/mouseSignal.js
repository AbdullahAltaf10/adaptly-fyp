// frontend/src/intervention/mouseSignal.js
/**
 * Weakest fusion signal (S4): is the mouse idle near a paragraph. Mouse
 * position alone is a weak proxy for reading position - many readers never
 * move the mouse while reading - so fusionScoring.js gives it the lowest
 * weight and only uses it as a tie-breaker.
 */
import { useCallback, useEffect, useRef } from "react";

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

  /**
   * Read at fusion-tick time, not on every render. Stable identity (empty
   * deps, reads only from refs) so a consumer's own effect that depends on
   * this getter - useDwellFusion's polling interval - is not torn down and
   * recreated on every render.
   */
  return useCallback(function getMouseSignal() {
    if (!positionRef.current) return null;
    const idle = Date.now() - lastMoveRef.current >= IDLE_MS;
    return { x: positionRef.current.x, y: positionRef.current.y, idle };
  }, []);
}

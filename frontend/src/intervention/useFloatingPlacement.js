/**
 * Smart auto-placement for the paragraph popup: flips to whichever side
 * (left/right/top/bottom) actually has room, and shifts along the axis to
 * stay inside the viewport, rather than a fixed "always on the right" rule.
 *
 * Uses Floating UI (https://floating-ui.com) - the established solution for
 * this exact anchored-overlay-with-collision-avoidance problem - instead of
 * a hand-rolled viewport-space heuristic. flip() tries the opposite side
 * when the preferred one would clip; shift() then nudges along the
 * remaining axis so the popup never goes off-screen even when no side has
 * full room.
 */
import { useCallback, useEffect, useState } from "react";
import { autoUpdate, computePosition, flip, offset, shift } from "@floating-ui/dom";

const GAP_PX = 12;

export function useFloatingPlacement(referenceElement, { enabled = true, placement = "right-start" } = {}) {
  const [floatingElement, setFloatingElement] = useState(null);
  const floatingRef = useCallback((node) => setFloatingElement(node), []);
  const [state, setState] = useState({ x: 0, y: 0, placement, ready: false });

  useEffect(() => {
    if (!enabled || !referenceElement || !floatingElement) {
      setState((current) => (current.ready ? { ...current, ready: false } : current));
      return undefined;
    }

    function update() {
      computePosition(referenceElement, floatingElement, {
        placement,
        middleware: [offset(GAP_PX), flip(), shift({ padding: 8 })],
      }).then((result) => {
        setState({ x: result.x, y: result.y, placement: result.placement, ready: true });
      });
    }

    update();
    return autoUpdate(referenceElement, floatingElement, update);
  }, [enabled, referenceElement, floatingElement, placement]);

  return { floatingRef, ...state };
}

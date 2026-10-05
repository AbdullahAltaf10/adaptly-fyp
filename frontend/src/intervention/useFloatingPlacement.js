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

// A last-resort safety net, applied AFTER flip()/shift() have already done
// their collision avoidance against the reference element. flip()/shift()
// only reason about the reference element's own box - when that box is
// itself mostly or entirely off-screen (e.g. a single paragraph tall enough
// to fill the whole viewport, with nothing else visible), their output can
// still place the floating element's OWN box mostly below the fold, leaving
// only its top edge (a toolbar row) visible until the learner scrolls. This
// clamps the final x/y so the floating element's own rendered box always
// fits inside the current viewport, regardless of where the reference
// element's box is.
const VIEWPORT_PADDING_PX = 8;

function clampToViewport(x, y, floatingElement) {
  const rect = floatingElement.getBoundingClientRect();
  const maxX = Math.max(window.innerWidth - rect.width - VIEWPORT_PADDING_PX, VIEWPORT_PADDING_PX);
  const maxY = Math.max(window.innerHeight - rect.height - VIEWPORT_PADDING_PX, VIEWPORT_PADDING_PX);
  return {
    x: Math.min(Math.max(x, VIEWPORT_PADDING_PX), maxX),
    y: Math.min(Math.max(y, VIEWPORT_PADDING_PX), maxY),
  };
}

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
        const { x, y } = clampToViewport(result.x, result.y, floatingElement);
        setState({ x, y, placement: result.placement, ready: true });
      });
    }

    update();
    return autoUpdate(referenceElement, floatingElement, update);
  }, [enabled, referenceElement, floatingElement, placement]);

  return { floatingRef, ...state };
}

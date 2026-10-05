/**
 * Adds paragraph-identity-based auto-close on top of the existing
 * useIntervention(): the popup stays open for as long as the learner is
 * anywhere in the SAME paragraph (activeChunkId === the intervention's own
 * chunk_id) - however long, regardless of which word or line inside it -
 * and closes only once a DIFFERENT chunk (or no chunk) has been the answer
 * continuously for PARAGRAPH_CHANGE_CONFIRM_MS. This is a flicker guard, not
 * a re-trigger on every momentary look-away; returning before the window
 * elapses cancels the close entirely (see the design spec, section 4.2).
 *
 * Depends only on primitive values and useIntervention's own stable
 * `complete` callback - never on the whole `intervention` object, which is
 * a fresh literal every render (the exact class of bug fixed in the prior
 * plan's Critical 1: depending on an unstable object identity tears down
 * and recreates effects on every render).
 */
import { useEffect, useRef, useState } from "react";

export const PARAGRAPH_CHANGE_CONFIRM_MS = 3000;

export function useParagraphPopup({ intervention, activeChunkId }) {
  const [collapsed, setCollapsed] = useState(false);
  const timerRef = useRef(null);

  const currentInterventionId = intervention.current?.intervention_id ?? null;
  const currentChunkId = intervention.current?.chunk_id ?? null;
  const complete = intervention.complete;

  useEffect(() => {
    if (!currentInterventionId) {
      setCollapsed(false);
      return undefined;
    }

    const stillOnSameParagraph = activeChunkId === currentChunkId;

    if (stillOnSameParagraph) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return undefined;
    }

    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      complete();
    }, PARAGRAPH_CHANGE_CONFIRM_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [activeChunkId, currentInterventionId, currentChunkId, complete]);

  return {
    ...intervention,
    collapsed,
    toggleCollapsed: () => setCollapsed((value) => !value),
  };
}

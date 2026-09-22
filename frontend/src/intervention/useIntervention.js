/**
 * Owns what happens to an intervention after the server offers one.
 *
 * Why this is a hook and not a few lines in the page
 * --------------------------------------------------
 * Every intervention starts at `offered`, and Module 8 measures recovery from
 * no such status. An intervention that is rendered and never reported stays at
 * `offered` for ever: the event is stored, the dashboard is empty, and nothing
 * anywhere raises. That failure is invisible from the browser, so the reporting
 * is kept in one tested place rather than spread across three components that
 * each have to remember.
 *
 * The status that counts differs by type - `displayed` for a simplification,
 * `accepted` for a break suggestion - which is why the two learner-initiated
 * components have an explicit accept action and the automatic ones do not.
 *
 * Failures never block the learner
 * --------------------------------
 * If the text cannot be generated, `failed` is reported and nothing is shown.
 * That is not just tidiness: the backend releases its cooldown on `failed`, so
 * a model outage costs the learner one missed intervention rather than two
 * minutes of silence.
 *
 * Reporting itself is best effort. A dropped status report must not leave an
 * intervention stuck on screen, so the UI advances either way and the server
 * treats a repeat of the same status as a no-op for when a retry does arrive.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchContent, reportStatus } from "./api";
import {
  STATUS_DISMISSED,
  STATUS_DISPLAYED,
  STATUS_ACCEPTED,
  STATUS_COMPLETED,
  STATUS_FAILED,
  needsGeneratedText,
} from "./constants";

export function useIntervention({ intervention, sessionId } = {}) {
  const [current, setCurrent] = useState(null);
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [accepted, setAccepted] = useState(false);

  // Which statuses have already been sent, per intervention id. Guards against
  // re-reporting across re-renders; the server is idempotent, but a request
  // per render is still a request per render.
  const reportedRef = useRef(new Map());
  const currentRef = useRef(null);

  const report = useCallback(
    async (interventionId, status) => {
      if (!interventionId || !sessionId) return false;
      const sent = reportedRef.current.get(interventionId) ?? new Set();
      if (sent.has(status)) return true;
      sent.add(status);
      reportedRef.current.set(interventionId, sent);
      try {
        await reportStatus(interventionId, { sessionId, status });
        return true;
      } catch {
        // Best effort. Letting this throw would strand the intervention on
        // screen over a dropped request, which is worse than a lost status.
        sent.delete(status);
        return false;
      }
    },
    [sessionId]
  );

  useEffect(() => {
    const offered = intervention;
    if (!offered?.intervention_id) return undefined;

    // A new intervention arriving while one is still open does NOT dismiss the
    // old one. Two reasons: the learner did not dismiss it, so saying they did
    // would be false; and for an automatic type already at `displayed`, moving
    // it to `dismissed` currently removes it from Module 8's recovery metrics
    // altogether (issue #46). Leaving it where it is keeps the record honest.
    if (currentRef.current?.intervention_id === offered.intervention_id) {
      return undefined;
    }

    let cancelled = false;
    currentRef.current = offered;
    setAccepted(false);
    setContent(null);

    async function open() {
      if (needsGeneratedText(offered.intervention_type)) {
        setLoading(true);
        try {
          const res = await fetchContent(offered.intervention_id);
          if (cancelled) return;
          setContent(res.data);
        } catch {
          // Nothing to show, so nothing reached the learner. `failed` is the
          // truthful status and it gives the cooldown back.
          if (!cancelled) {
            report(offered.intervention_id, STATUS_FAILED);
            currentRef.current = null;
            setCurrent(null);
          }
          return;
        } finally {
          if (!cancelled) setLoading(false);
        }
      }

      if (cancelled) return;
      setCurrent(offered);
      // Reported after the content is in hand, so `displayed` means it really
      // was on screen rather than that a request was started.
      report(offered.intervention_id, STATUS_DISPLAYED);
    }

    open();
    return () => {
      cancelled = true;
    };
  }, [intervention, report]);

  const close = useCallback(
    (status) => {
      const open = currentRef.current;
      if (!open) return;
      report(open.intervention_id, status);
      currentRef.current = null;
      setCurrent(null);
      setContent(null);
      setAccepted(false);
    },
    [report]
  );

  /**
   * The learner took it up. This is the status that starts measurement for a
   * break suggestion or an assistant prompt, so it is the whole reason those
   * two have a button at all.
   *
   * It does not close: a break is not over the moment it is accepted, and the
   * assistant needs somewhere to appear. `complete` ends it.
   */
  const accept = useCallback(() => {
    const open = currentRef.current;
    if (!open) return;
    setAccepted(true);
    report(open.intervention_id, STATUS_ACCEPTED);
  }, [report]);

  const complete = useCallback(() => close(STATUS_COMPLETED), [close]);
  const dismiss = useCallback(() => close(STATUS_DISMISSED), [close]);

  return { current, content, loading, accepted, accept, complete, dismiss };
}

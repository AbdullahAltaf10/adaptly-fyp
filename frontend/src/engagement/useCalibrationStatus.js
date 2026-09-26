/**
 * Whether the learner has calibrated, for the pre-session screen.
 *
 * Three answers, not two, because "we could not find out" must not be
 * presented as "you have not calibrated":
 *
 *   true   - they have
 *   false  - they have not
 *   null   - unknown (still loading, or the request failed)
 *
 * Failing quietly to `null` is deliberate. This is advice, not a gate: a
 * network blip while checking must never stop someone studying, and telling
 * them they are uncalibrated on the strength of a failed request would be a
 * false statement about their own setup.
 */

import { useEffect, useState } from "react";

import { fetchCalibrationStatus } from "./api";

export function useCalibrationStatus({ enabled = true } = {}) {
  const [calibrated, setCalibrated] = useState(null);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    fetchCalibrationStatus()
      .then((response) => {
        if (!cancelled) setCalibrated(response.data?.calibrated === true);
      })
      .catch(() => {
        if (!cancelled) setCalibrated(null);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return calibrated;
}

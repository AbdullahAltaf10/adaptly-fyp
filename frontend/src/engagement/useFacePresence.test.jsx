/**
 * Tests for the out-of-frame debounce.
 *
 * This hook exists because reporting "no face" directly made the overlay
 * flicker: MediaPipe misses the occasional frame even when nobody has moved.
 * The debounce is the whole point of the hook, and it is timing logic, so it
 * is worth testing with a fake clock rather than by watching the screen.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FACE_LOST_GRACE_MS, RECALIBRATE_SUGGEST_MS } from "./constants";
import { useFacePresence } from "./useFacePresence";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const advance = (ms) => act(() => vi.advanceTimersByTime(ms));

function setup(props = {}) {
  return renderHook(
    (p) => useFacePresence({ enabled: true, calibrated: true, ...p }),
    { initialProps: { faceDetected: true, ...props } }
  );
}

describe("useFacePresence", () => {
  it("does not report a loss immediately", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(FACE_LOST_GRACE_MS - 100);

    expect(result.current.faceLost).toBe(false);
  });

  it("reports a loss once the grace period has passed", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(FACE_LOST_GRACE_MS);

    expect(result.current.faceLost).toBe(true);
  });

  /**
   * The behaviour the hook exists for: a single dropped frame must not show
   * the overlay at all.
   */
  it("ignores a brief dropout", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(200);
    rerender({ faceDetected: true });
    advance(FACE_LOST_GRACE_MS * 2);

    expect(result.current.faceLost).toBe(false);
    expect(result.current.showTick).toBe(false);
  });

  it("clears the loss and shows a confirmation when the face returns", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(FACE_LOST_GRACE_MS);
    rerender({ faceDetected: true });

    expect(result.current.faceLost).toBe(false);
    expect(result.current.showTick).toBe(true);
  });

  /**
   * A long absence usually means the learner got up or changed seat, which
   * makes the calibration baseline stale. Short absences must not nag.
   */
  it("suggests recalibrating only after a long absence", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(FACE_LOST_GRACE_MS + 200);
    rerender({ faceDetected: true });

    expect(result.current.suggestRecalibrate).toBe(false);
  });

  /**
   * Note the clock this measures against: the absence is timed from when the
   * loss is *confirmed*, not from when the face disappeared, because
   * `lostAtRef` is set inside the grace-period timeout. So a learner has to be
   * away for the grace period plus the suggestion threshold before being
   * prompted. That is a deliberate under-count rather than a bug — it measures
   * confirmed absence — but it is surprising enough to pin.
   */
  it("suggests recalibrating after a long absence", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(FACE_LOST_GRACE_MS + RECALIBRATE_SUGGEST_MS + 500);
    rerender({ faceDetected: true });

    expect(result.current.suggestRecalibrate).toBe(true);
  });

  /**
   * Nothing to recalibrate against if they never calibrated, so prompting
   * would be noise.
   */
  it("does not suggest recalibrating when never calibrated", () => {
    const { result, rerender } = setup({ calibrated: false });

    rerender({ faceDetected: false, calibrated: false });
    advance(FACE_LOST_GRACE_MS + RECALIBRATE_SUGGEST_MS + 500);
    rerender({ faceDetected: true, calibrated: false });

    expect(result.current.suggestRecalibrate).toBe(false);
  });

  it("can be dismissed", () => {
    const { result, rerender } = setup();

    rerender({ faceDetected: false });
    advance(FACE_LOST_GRACE_MS + RECALIBRATE_SUGGEST_MS + 500);
    rerender({ faceDetected: true });
    expect(result.current.suggestRecalibrate).toBe(true);

    act(() => result.current.dismissRecalibrate());
    expect(result.current.suggestRecalibrate).toBe(false);
  });

  /** Before the session starts there is no camera, so nothing to report. */
  it("stays quiet while disabled", () => {
    const { result, rerender } = setup({ enabled: false });

    rerender({ faceDetected: false, enabled: false });
    advance(FACE_LOST_GRACE_MS * 3);

    expect(result.current.faceLost).toBe(false);
  });
});

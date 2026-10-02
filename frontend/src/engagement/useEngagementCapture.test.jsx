/**
 * Minimal harness for useEngagementCapture, scoped to the one new behavior
 * this task adds: getLatestLandmarks(). The hook's existing prediction/
 * calibration/session-lifecycle behavior is exercised indirectly elsewhere
 * (StudySession's own tests) and is out of scope here.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./faceLandmarker", () => ({
  createFaceLandmarker: vi.fn(() =>
    Promise.resolve({
      detectForVideo: vi.fn(() => ({
        faceLandmarks: [Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5, z: 0 }))],
      })),
      close: vi.fn(),
    })
  ),
  closeFaceLandmarker: vi.fn(),
}));

const fetchCalibrationStatusMock = vi.fn(() => Promise.resolve({ data: { calibrated: true } }));
vi.mock("./api", () => ({
  startSession: vi.fn(() => Promise.resolve({})),
  endSession: vi.fn(() => Promise.resolve({})),
  calibrate: vi.fn(() => Promise.resolve({})),
  analyze: vi.fn(() => Promise.resolve({ data: null })),
  fetchCalibrationStatus: () => fetchCalibrationStatusMock(),
}));

import { useEngagementCapture } from "./useEngagementCapture";
import { CALIBRATION_FRAMES, CALIBRATION_INTERVAL_MS, CAPTURE_INTERVAL_MS } from "./constants";
import { calibrate as calibrateMock } from "./api";

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("navigator", {
    ...navigator,
    mediaDevices: {
      getUserMedia: vi.fn(() => Promise.resolve({ getTracks: () => [{ stop: vi.fn() }] })),
    },
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Mounts the hook and lets setup()'s getUserMedia -> createFaceLandmarker ->
 * startSession chain resolve, then attaches a fake video element the same
 * way a real <video ref={videoRef}> would. */
async function renderCapture() {
  const hook = renderHook(() => useEngagementCapture({ active: true }));
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  hook.result.current.videoRef.current = document.createElement("video");
  return hook;
}

describe("useEngagementCapture: silent first-session auto-calibration", () => {
  // 2026-09-30 audit: the pre-session dialog's only "Calibrate" button
  // calibrates WebGazer, not this - Module 3's own per-user baseline was
  // only ever recorded if a learner found and clicked the separate,
  // unprompted "Calibrate now" button mid-session. /calibrate's own
  // docstring already says "without this, attentive users are classified
  // as distracted". This silently runs the exact same calibration a
  // learner would have triggered manually, using their own first few
  // seconds, but only on a learner's first-ever session (checked via
  // fetchCalibrationStatus) so a returning, already-calibrated learner's
  // session id is not churned on every single visit.
  beforeEach(() => {
    fetchCalibrationStatusMock.mockReset();
    calibrateMock.mockClear();
  });

  async function renderAndAttachVideo({ calibrated }) {
    fetchCalibrationStatusMock.mockResolvedValue({ data: { calibrated } });
    const hook = renderHook(() => useEngagementCapture({ active: true }));
    hook.result.current.videoRef.current = document.createElement("video");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CALIBRATION_FRAMES * CALIBRATION_INTERVAL_MS + 500);
    });
    return hook;
  }

  it("silently calibrates a never-calibrated learner, with no manual click", async () => {
    const { result } = await renderAndAttachVideo({ calibrated: false });
    expect(fetchCalibrationStatusMock).toHaveBeenCalledTimes(1);
    expect(calibrateMock).toHaveBeenCalledTimes(1);
    expect(result.current.calibrated).toBe(true);
    expect(result.current.ready).toBe(true);
  });

  it("does not auto-calibrate an already-calibrated returning learner", async () => {
    const { result } = await renderAndAttachVideo({ calibrated: true });
    expect(fetchCalibrationStatusMock).toHaveBeenCalledTimes(1);
    expect(calibrateMock).not.toHaveBeenCalled();
    expect(result.current.ready).toBe(true);
  });

  it("still becomes ready even if the calibration-status check itself fails", async () => {
    fetchCalibrationStatusMock.mockRejectedValue(new Error("network"));
    const hook = renderHook(() => useEngagementCapture({ active: true }));
    hook.result.current.videoRef.current = document.createElement("video");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CALIBRATION_FRAMES * CALIBRATION_INTERVAL_MS + 500);
    });
    expect(calibrateMock).not.toHaveBeenCalled();
    expect(hook.result.current.ready).toBe(true);
  });
});

describe("useEngagementCapture: getLatestLandmarks", () => {
  it("returns null before any frame has been captured", () => {
    const { result } = renderHook(() => useEngagementCapture({ active: true }));
    expect(result.current.getLatestLandmarks()).toBeNull();
  });

  it("exposes the most recent frame's landmarks via getLatestLandmarks()", async () => {
    const { result } = await renderCapture();
    await act(async () => {
      vi.advanceTimersByTime(CAPTURE_INTERVAL_MS);
    });
    expect(result.current.getLatestLandmarks()).not.toBeNull();
    expect(Array.isArray(result.current.getLatestLandmarks())).toBe(true);
  });
});

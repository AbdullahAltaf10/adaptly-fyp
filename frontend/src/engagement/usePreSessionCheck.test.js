/**
 * The WebGazer click-calibration flow added alongside addMouseEventListeners()
 * (see webgazerSignal.js's own docstring for why that call was missing):
 * a single "Calibrate" click used to flip webgazerStatus straight to "ready"
 * even though WebGazer had not been given a single training sample yet.
 * This hook now requires CALIBRATION_POINT_COUNT real clicks, at real
 * on-screen positions, before reporting "ready" - each one is a genuine
 * (x, y) training sample for WebGazer's regression, now that
 * addMouseEventListeners() is wired up to actually consume them.
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const calibrateWebgazer = vi.fn();
const stopWebgazer = vi.fn();
vi.mock("./webgazerSignal", () => ({
  calibrateWebgazer: (...args) => calibrateWebgazer(...args),
  stopWebgazer: (...args) => stopWebgazer(...args),
  CALIBRATION_POINTS: [
    { x: 0.1, y: 0.1 },
    { x: 0.9, y: 0.1 },
    { x: 0.5, y: 0.92 },
    { x: 0.1, y: 0.9 },
    { x: 0.9, y: 0.9 },
  ],
}));

// enabled: false (passed to every usePreSessionCheck() call below) skips the
// hook's own camera probe effect entirely, so these tests - which are only
// about the WebGazer click-calibration state machine - never touch
// getUserMedia at all.
beforeEach(() => {
  calibrateWebgazer.mockReset();
  stopWebgazer.mockReset();
});

describe("usePreSessionCheck - WebGazer click calibration", () => {
  it("does not report ready the moment calibrateWebgazer resolves - real clicks are still required", async () => {
    calibrateWebgazer.mockResolvedValue({ available: true });
    const { result } = renderHook(() => usePreSessionCheckImport());

    await act(async () => {
      await result.current.startWebgazerCalibration();
    });

    expect(result.current.webgazerStatus).toBe("awaiting-points");
  });

  it("reports ready only once every calibration point has been clicked", async () => {
    calibrateWebgazer.mockResolvedValue({ available: true });
    const { result } = renderHook(() => usePreSessionCheckImport());

    await act(async () => {
      await result.current.startWebgazerCalibration();
    });

    act(() => result.current.recordCalibrationPoint(0));
    act(() => result.current.recordCalibrationPoint(1));
    act(() => result.current.recordCalibrationPoint(2));
    act(() => result.current.recordCalibrationPoint(3));
    expect(result.current.webgazerStatus).toBe("awaiting-points");

    act(() => result.current.recordCalibrationPoint(4));
    expect(result.current.webgazerStatus).toBe("ready");
  });

  it("clicking the same point twice does not count twice", async () => {
    calibrateWebgazer.mockResolvedValue({ available: true });
    const { result } = renderHook(() => usePreSessionCheckImport());

    await act(async () => {
      await result.current.startWebgazerCalibration();
    });

    act(() => {
      result.current.recordCalibrationPoint(0);
      result.current.recordCalibrationPoint(0);
      result.current.recordCalibrationPoint(0);
    });
    expect(result.current.webgazerStatus).toBe("awaiting-points");
    expect(result.current.calibrationPointsClicked.size).toBe(1);
  });

  it("goes straight to unavailable when WebGazer itself could not start", async () => {
    calibrateWebgazer.mockResolvedValue({ available: false, reason: "camera denied" });
    const { result } = renderHook(() => usePreSessionCheckImport());

    await act(async () => {
      await result.current.startWebgazerCalibration();
    });

    expect(result.current.webgazerStatus).toBe("unavailable");
  });

  it("skipping goes straight to unavailable without ever calling calibrateWebgazer", () => {
    const { result } = renderHook(() => usePreSessionCheckImport());
    act(() => result.current.skipWebgazerCalibration());
    expect(result.current.webgazerStatus).toBe("unavailable");
    expect(calibrateWebgazer).not.toHaveBeenCalled();
  });
});

// Imported lazily, after the mock above is registered, matching this
// project's established pattern for hooks that import a mocked module.
import { usePreSessionCheck } from "./usePreSessionCheck";
function usePreSessionCheckImport() {
  return usePreSessionCheck({ enabled: false });
}

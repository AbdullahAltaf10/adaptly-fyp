import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock is hoisted above every import and const, so the mock function has to
// be created in vi.hoisted too or the factory reads it before it exists.
const { fetchCalibrationStatus } = vi.hoisted(() => ({ fetchCalibrationStatus: vi.fn() }));
vi.mock("./api", () => ({ fetchCalibrationStatus }));

import { useCalibrationStatus } from "./useCalibrationStatus";

beforeEach(() => {
  fetchCalibrationStatus.mockReset();
});

describe("three answers, not two", () => {
  it("is null while it does not yet know", () => {
    fetchCalibrationStatus.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCalibrationStatus());
    expect(result.current).toBeNull();
  });

  it("reports true when the learner has calibrated", async () => {
    fetchCalibrationStatus.mockResolvedValue({ data: { calibrated: true } });
    const { result } = renderHook(() => useCalibrationStatus());
    await waitFor(() => expect(result.current).toBe(true));
  });

  it("reports false when they have not", async () => {
    fetchCalibrationStatus.mockResolvedValue({ data: { calibrated: false } });
    const { result } = renderHook(() => useCalibrationStatus());
    await waitFor(() => expect(result.current).toBe(false));
  });

  it("stays null when the request fails, never false", async () => {
    // "We could not check" must not become "you have not calibrated": that
    // would be a false statement about the learner's own setup, made because of
    // a network blip.
    fetchCalibrationStatus.mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useCalibrationStatus());
    await waitFor(() => expect(fetchCalibrationStatus).toHaveBeenCalled());
    expect(result.current).toBeNull();
  });

  it("treats anything other than an explicit true as not calibrated", async () => {
    fetchCalibrationStatus.mockResolvedValue({ data: { calibrated: "yes" } });
    const { result } = renderHook(() => useCalibrationStatus());
    await waitFor(() => expect(result.current).toBe(false));
  });
});

describe("when it should not ask", () => {
  it("makes no request while disabled", () => {
    renderHook(() => useCalibrationStatus({ enabled: false }));
    expect(fetchCalibrationStatus).not.toHaveBeenCalled();
  });

  it("ignores a response that arrives after unmounting", async () => {
    let resolve;
    fetchCalibrationStatus.mockReturnValue(new Promise((r) => (resolve = r)));
    const { result, unmount } = renderHook(() => useCalibrationStatus());
    unmount();
    resolve({ data: { calibrated: true } });
    await Promise.resolve();
    expect(result.current).toBeNull();
  });
});

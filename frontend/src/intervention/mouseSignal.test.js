// frontend/src/intervention/mouseSignal.test.js
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useMouseSignal } from "./mouseSignal";

function moveMouseTo(x, y) {
  act(() => {
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: x, clientY: y }));
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useMouseSignal", () => {
  it("returns null before any mouse movement has ever been seen", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    expect(result.current()).toBeNull();
  });

  it("reports the last position as NOT idle immediately after moving", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(120, 240);
    expect(result.current()).toEqual({ x: 120, y: 240, idle: false });
  });

  it("reports idle=true once 1500ms pass with no further movement", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(50, 60);
    act(() => vi.advanceTimersByTime(1500));
    expect(result.current()).toEqual({ x: 50, y: 60, idle: true });
  });

  it("resets idle back to false on a fresh movement", () => {
    const { result } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(10, 10);
    act(() => vi.advanceTimersByTime(1500));
    expect(result.current().idle).toBe(true);
    moveMouseTo(11, 11);
    expect(result.current().idle).toBe(false);
  });

  it("stops listening on unmount", () => {
    const { result, unmount } = renderHook(() => useMouseSignal({ enabled: true }));
    moveMouseTo(1, 1);
    unmount();
    moveMouseTo(2, 2); // must not throw, and has no observer left to update
    expect(result.current()).toEqual({ x: 1, y: 1, idle: false });
  });

  it("returns the same getter identity across re-renders", () => {
    // A fresh function every render would reset any effect elsewhere that
    // depends on this getter's identity (e.g. useDwellFusion's polling
    // interval), tearing it down and recreating it on every parent render.
    const { result, rerender } = renderHook(() => useMouseSignal({ enabled: true }));
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const computePosition = vi.fn();
const autoUpdate = vi.fn();
vi.mock("@floating-ui/dom", () => ({
  computePosition: (...args) => computePosition(...args),
  autoUpdate: (...args) => autoUpdate(...args),
  offset: (v) => ({ name: "offset", v }),
  flip: (v) => ({ name: "flip", v }),
  shift: (v) => ({ name: "shift", v }),
}));

import { useFloatingPlacement } from "./useFloatingPlacement";

function el() {
  return document.createElement("div");
}

beforeEach(() => {
  computePosition.mockReset();
  autoUpdate.mockReset();
  autoUpdate.mockReturnValue(vi.fn()); // cleanup fn
});
afterEach(() => vi.restoreAllMocks());

describe("useFloatingPlacement", () => {
  it("is not ready when there is no reference element", () => {
    const { result } = renderHook(() => useFloatingPlacement(null));
    expect(result.current.ready).toBe(false);
    expect(computePosition).not.toHaveBeenCalled();
  });

  it("is not ready until the floating element is attached via floatingRef", () => {
    const reference = el();
    const { result } = renderHook(() => useFloatingPlacement(reference));
    expect(result.current.ready).toBe(false);
    expect(computePosition).not.toHaveBeenCalled();
  });

  it("computes position once both the reference and floating elements are present", async () => {
    const reference = el();
    let resolvePosition;
    computePosition.mockReturnValue(
      new Promise((resolve) => {
        resolvePosition = resolve;
      })
    );

    const { result } = renderHook(() => useFloatingPlacement(reference));
    act(() => result.current.floatingRef(el()));

    expect(computePosition).toHaveBeenCalledTimes(1);
    await act(async () => {
      // Well inside a default jsdom viewport (1024x768) for a zero-size
      // floating element, so clamping never engages - this test is only
      // about the passthrough wiring, not clamping (see the dedicated
      // clamping tests below).
      resolvePosition({ x: 200, y: 150, placement: "left-start" });
      await Promise.resolve();
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.x).toBe(200);
    expect(result.current.y).toBe(150);
    expect(result.current.placement).toBe("left-start");
  });

  it("clamps the result inside the viewport when the reference element is large enough that flip/shift still leaves the floating element partly off-screen", async () => {
    // The real-world trigger: a single paragraph that fills the whole
    // viewport (nothing else on screen), so the anchor math can still
    // place the popup's own box mostly below the fold - only its top
    // toolbar visible until the learner scrolls.
    window.innerWidth = 1024;
    window.innerHeight = 768;
    const reference = el();
    computePosition.mockReturnValue(Promise.resolve({ x: 900, y: 700, placement: "right-start" }));

    const { result } = renderHook(() => useFloatingPlacement(reference));
    const floating = el();
    Object.defineProperty(floating, "getBoundingClientRect", {
      value: () => ({ width: 320, height: 360 }),
    });
    await act(async () => {
      result.current.floatingRef(floating);
      await Promise.resolve();
    });

    // Must fit fully within the viewport: x + width <= innerWidth, y + height <= innerHeight.
    expect(result.current.x + 320).toBeLessThanOrEqual(1024);
    expect(result.current.y + 360).toBeLessThanOrEqual(768);
  });

  it("never clamps to a negative position when the floating element is larger than the viewport", async () => {
    window.innerWidth = 1024;
    window.innerHeight = 768;
    const reference = el();
    computePosition.mockReturnValue(Promise.resolve({ x: 900, y: 700, placement: "right-start" }));

    const { result } = renderHook(() => useFloatingPlacement(reference));
    const floating = el();
    Object.defineProperty(floating, "getBoundingClientRect", {
      value: () => ({ width: 2000, height: 2000 }),
    });
    await act(async () => {
      result.current.floatingRef(floating);
      await Promise.resolve();
    });

    expect(result.current.x).toBeGreaterThanOrEqual(0);
    expect(result.current.y).toBeGreaterThanOrEqual(0);
  });

  it("subscribes with autoUpdate and cleans it up on unmount", () => {
    const reference = el();
    computePosition.mockReturnValue(new Promise(() => {}));
    const cleanup = vi.fn();
    autoUpdate.mockReturnValue(cleanup);

    const { result, unmount } = renderHook(() => useFloatingPlacement(reference));
    act(() => result.current.floatingRef(el()));

    expect(autoUpdate).toHaveBeenCalledTimes(1);
    unmount();
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it("never computes anything while disabled", () => {
    const reference = el();
    const { result } = renderHook(() => useFloatingPlacement(reference, { enabled: false }));
    act(() => result.current.floatingRef(el()));
    expect(computePosition).not.toHaveBeenCalled();
    expect(autoUpdate).not.toHaveBeenCalled();
  });
});

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
      resolvePosition({ x: 42, y: 7, placement: "left-start" });
      await Promise.resolve();
    });

    expect(result.current.ready).toBe(true);
    expect(result.current.x).toBe(42);
    expect(result.current.y).toBe(7);
    expect(result.current.placement).toBe("left-start");
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

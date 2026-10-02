/**
 * The dwell hook exposes the active chunk two ways on purpose: a getter for
 * the capture loop (read at send time, no render) and a state value for the
 * study page (drives a render). StudySession once used the getter where it
 * needed the value, and every test hid it because they all mock this hook.
 * These tests use the real one.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDwell } from "./useDwell";

let observers = [];

class FakeIntersectionObserver {
  constructor(callback) {
    this.callback = callback;
    this.targets = new Set();
    observers.push(this);
  }
  observe(target) {
    this.targets.add(target);
  }
  unobserve(target) {
    this.targets.delete(target);
  }
  disconnect() {
    this.targets.clear();
  }
}

function see(element, ratio) {
  act(() => {
    observers.forEach((observer) => {
      observer.callback([{ target: element, intersectionRatio: ratio }]);
    });
  });
}

beforeEach(() => {
  observers = [];
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useDwell: which chunk is being read", () => {
  it("exposes the chunk as a getter for the capture loop", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    expect(typeof result.current.chunkId).toBe("function");
    expect(result.current.chunkId()).toBeNull();
  });

  it("reports the most visible chunk through BOTH shapes", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    const first = document.createElement("section");
    const second = document.createElement("section");

    act(() => {
      result.current.register("0", first);
      result.current.register("1", second);
    });
    see(first, 0.3);
    see(second, 0.9);

    // The value drives a render...
    expect(result.current.activeChunkId).toBe("1");
    // ...and the getter is what a window carries when it is sent.
    expect(result.current.chunkId()).toBe("1");
  });

  it("follows the learner as the more visible chunk changes", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    const first = document.createElement("section");
    const second = document.createElement("section");
    act(() => {
      result.current.register("0", first);
      result.current.register("1", second);
    });

    see(first, 1);
    see(second, 0);
    expect(result.current.activeChunkId).toBe("0");

    see(first, 0);
    see(second, 1);
    expect(result.current.activeChunkId).toBe("1");
    expect(result.current.chunkId()).toBe("1");
  });

  it("reports nothing when no chunk is on screen", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    const only = document.createElement("section");
    act(() => result.current.register("0", only));

    see(only, 0.6);
    expect(result.current.activeChunkId).toBe("0");

    see(only, 0);
    expect(result.current.activeChunkId).toBeNull();
    expect(result.current.chunkId()).toBeNull();
  });

  it("starts dwell from zero on each newly active chunk", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    const first = document.createElement("section");
    act(() => result.current.register("0", first));
    see(first, 1);
    expect(result.current.seconds()).toBeGreaterThanOrEqual(0);
    expect(result.current.seconds()).toBeLessThan(1);
  });

  it("exposes a read-only snapshot of every chunk's visibility ratio", () => {
    const { result } = renderHook(() => useDwell({ enabled: true }));
    const first = document.createElement("section");
    const second = document.createElement("section");
    act(() => {
      result.current.register("0", first);
      result.current.register("1", second);
    });
    see(first, 0.3);
    see(second, 0.9);
    expect(result.current.visibilityRatios()).toEqual(new Map([["0", 0.3], ["1", 0.9]]));
  });
});

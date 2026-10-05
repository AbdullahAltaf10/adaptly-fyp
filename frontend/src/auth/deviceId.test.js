import { beforeEach, describe, expect, it, vi } from "vitest";

import { getDeviceId } from "./deviceId";

describe("getDeviceId", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("generates and persists an id on first call", () => {
    const id = getDeviceId();
    expect(id).toBeTruthy();
    expect(window.localStorage.getItem("adaptly_device_id")).toBe(id);
  });

  it("returns the same id on later calls", () => {
    const first = getDeviceId();
    const second = getDeviceId();
    expect(second).toBe(first);
  });

  it("falls back to a fresh id when storage throws", () => {
    const spy = vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => getDeviceId()).not.toThrow();
    spy.mockRestore();
  });
});

/**
 * These settings were stored for months and never applied, and the one place
 * that tried read a key the backend does not have. So the tests are about the
 * two things that actually went wrong: reading the right field names, and the
 * settings reaching the document at all.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ACCESSIBILITY_FIELDS,
  DEFAULT_ACCESSIBILITY,
  FONT_CHOICES,
  LINE_SPACING_CHOICES,
  applyAccessibility,
  readStoredAccessibility,
  resolveAccessibility,
} from "./useAccessibility";

afterEach(() => {
  document.documentElement.removeAttribute("data-contrast");
  document.documentElement.removeAttribute("data-focus-isolation");
  document.documentElement.style.cssText = "";
  window.localStorage.clear();
});

describe("what the shared contract allows", () => {
  it("offers exactly the two fonts user-profile.schema.json allows", () => {
    expect(Object.keys(FONT_CHOICES).sort()).toEqual(["default", "opendyslexic"]);
  });

  it("stores line spacing as a number, never a name", () => {
    for (const preset of LINE_SPACING_CHOICES) {
      expect(typeof preset.value).toBe("number");
      expect(preset.value).toBeGreaterThanOrEqual(1);
      expect(preset.value).toBeLessThanOrEqual(3);
    }
    expect(typeof DEFAULT_ACCESSIBILITY.line_spacing).toBe("number");
  });

  it("defaults to what the backend writes for a new profile", () => {
    // users/models.py DEFAULT_ACCESSIBILITY: font "default", line_spacing 1.5
    expect(DEFAULT_ACCESSIBILITY.font).toBe("default");
    expect(DEFAULT_ACCESSIBILITY.line_spacing).toBe(1.5);
  });
});

describe("the field names the backend actually stores", () => {
  it("matches users/contracts.py ALLOWED_ACCESSIBILITY_KEYS exactly", () => {
    // The original bug: App.jsx read `accessibility_settings.contrast`, the
    // backend stores `high_contrast`, so high contrast never once turned on
    // and nothing failed loudly. Pinning the list is what stops that
    // recurring if either side adds a field.
    expect([...ACCESSIBILITY_FIELDS].sort()).toEqual(
      ["focus_isolation", "font", "high_contrast", "line_spacing"].sort()
    );
  });

  it("ignores a `contrast` key, which is what the broken code used", () => {
    applyAccessibility({ contrast: "high" });
    expect(document.documentElement.getAttribute("data-contrast")).toBeNull();
  });
});

describe("applying settings to the document", () => {
  it("turns high contrast on and off", () => {
    applyAccessibility({ high_contrast: true });
    expect(document.documentElement.getAttribute("data-contrast")).toBe("high");

    applyAccessibility({ high_contrast: false });
    expect(document.documentElement.getAttribute("data-contrast")).toBeNull();
  });

  it("sets the font stack and line height", () => {
    applyAccessibility({ font: "opendyslexic", line_spacing: 2.2 });
    const root = document.documentElement;
    expect(root.style.getPropertyValue("--font-sans")).toMatch(/OpenDyslexic/);
    expect(root.style.lineHeight).toBe("2.2");
  });

  it("toggles focus isolation", () => {
    applyAccessibility({ focus_isolation: true });
    expect(document.documentElement.getAttribute("data-focus-isolation")).toBe("on");
  });
});

describe("settings that arrive incomplete or wrong", () => {
  it("fills in the defaults rather than writing undefined into CSS", () => {
    const resolved = resolveAccessibility({ high_contrast: true });
    expect(resolved).toEqual({ ...DEFAULT_ACCESSIBILITY, high_contrast: true });
  });

  it("falls back when a stored value is not one we know", () => {
    // A profile written by an older or newer version must not produce
    // `--font-sans: undefined`, which silently drops to the browser default.
    const resolved = resolveAccessibility({ font: "comic-sans", line_spacing: "enormous" });
    expect(resolved.font).toBe(DEFAULT_ACCESSIBILITY.font);
    expect(resolved.line_spacing).toBe(DEFAULT_ACCESSIBILITY.line_spacing);
  });

  it("keeps a choice an older build stored under its old name", () => {
    // Earlier builds saved "serif" and "loose". Discarding them would reset
    // every existing learner's settings the day this shipped.
    const resolved = resolveAccessibility({ font: "serif", line_spacing: "loose" });
    expect(resolved.font).toBe("default");
    expect(resolved.line_spacing).toBe(2.2);
  });

  it("clamps line spacing into the contract's 1-3 range instead of rejecting it", () => {
    expect(resolveAccessibility({ line_spacing: 9 }).line_spacing).toBe(3);
    expect(resolveAccessibility({ line_spacing: 0.2 }).line_spacing).toBe(1);
    expect(resolveAccessibility({ line_spacing: 1.75 }).line_spacing).toBe(1.75);
  });

  it("does not accept NaN or Infinity as a line spacing", () => {
    expect(resolveAccessibility({ line_spacing: NaN }).line_spacing).toBe(
      DEFAULT_ACCESSIBILITY.line_spacing
    );
    expect(resolveAccessibility({ line_spacing: Infinity }).line_spacing).toBe(
      DEFAULT_ACCESSIBILITY.line_spacing
    );
  });

  it("coerces truthiness rather than trusting the type", () => {
    const resolved = resolveAccessibility({ high_contrast: "yes", focus_isolation: 0 });
    expect(resolved.high_contrast).toBe(true);
    expect(resolved.focus_isolation).toBe(false);
  });

  it("survives null", () => {
    expect(() => applyAccessibility(null)).not.toThrow();
  });
});

describe("remembering the preference before there is a profile", () => {
  it("returns null rather than throwing when storage is unavailable", () => {
    // Private windows and blocked site data both throw here. A learner in one
    // of those should get the defaults, not a blank page.
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readStoredAccessibility()).toBeNull();
    spy.mockRestore();
  });

  it("returns null for a corrupted value", () => {
    window.localStorage.setItem("adaptly.accessibility", "{not json");
    expect(readStoredAccessibility()).toBeNull();
  });
});

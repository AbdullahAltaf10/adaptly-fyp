/**
 * Applies the learner's saved accessibility settings to the document.
 *
 * Scope section 6.1: "Accessibility settings such as font choice, line
 * spacing, and contrast are saved to any profile type and applied
 * automatically at the start of every session." They were saved; nothing ever
 * applied them.
 *
 * There was also a real bug behind that. `App.jsx` read:
 *
 *     profile?.accessibility_settings?.contrast === "high"
 *
 * but the backend stores `high_contrast` (`users/contracts.py:26`, alongside
 * `font`, `line_spacing` and `focus_isolation`). There is no `contrast` key,
 * so the expression was always false and high-contrast mode had never once
 * turned on. The field names below are taken from that allowlist rather than
 * guessed, and `ACCESSIBILITY_FIELDS` in this file is the frontend's copy of
 * it — if the backend adds a field, both change together.
 *
 * Everything is written to <html> rather than passed down as props, because
 * `rem` sizing, the high-contrast theme and the focus ring all need to affect
 * portalled content and the document background too, not just React's tree.
 */

import { useEffect } from "react";

/** Mirrors backend `users/contracts.py:ACCESSIBILITY_FIELDS`. */
export const ACCESSIBILITY_FIELDS = ["font", "line_spacing", "high_contrast", "focus_isolation"];

/**
 * Named font choices rather than a free-text family.
 *
 * A learner picking "dyslexia-friendly" should get something measurably more
 * legible, not a font name we hope is installed. These are all system stacks,
 * so nothing has to download before the text renders - a webfont that arrives
 * late is its own accessibility problem.
 */
export const FONT_CHOICES = {
  system: { label: "System default", stack: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
  sans: { label: "Sans serif", stack: 'Verdana, Tahoma, "DejaVu Sans", sans-serif' },
  serif: { label: "Serif", stack: 'Georgia, "Times New Roman", serif' },
  mono: { label: "Monospace", stack: 'ui-monospace, "Cascadia Mono", Consolas, monospace' },
};

export const LINE_SPACING_CHOICES = {
  compact: { label: "Compact", value: 1.4 },
  normal: { label: "Normal", value: 1.6 },
  relaxed: { label: "Relaxed", value: 1.9 },
  loose: { label: "Loose", value: 2.2 },
};

export const DEFAULT_ACCESSIBILITY = {
  font: "system",
  line_spacing: "normal",
  high_contrast: false,
  focus_isolation: false,
};

/**
 * Settings are stored per profile, but the sign-in and registration screens
 * come *before* there is a profile to read. Mirroring them into localStorage
 * means a learner who needs high contrast gets it on the screen where they
 * type their password, not only after they are through it.
 */
const STORAGE_KEY = "adaptly.accessibility";

export function readStoredAccessibility() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    // Private windows, blocked site data, or a corrupted value. The defaults
    // are a perfectly good answer, so this must never throw into render.
    return null;
  }
}

function storeAccessibility(settings) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Not being able to remember the preference is survivable; crashing is not.
  }
}

/** Fills in anything missing, so a partial profile cannot produce undefined CSS. */
export function resolveAccessibility(settings) {
  const merged = { ...DEFAULT_ACCESSIBILITY, ...(settings || {}) };
  return {
    font: FONT_CHOICES[merged.font] ? merged.font : DEFAULT_ACCESSIBILITY.font,
    line_spacing: LINE_SPACING_CHOICES[merged.line_spacing]
      ? merged.line_spacing
      : DEFAULT_ACCESSIBILITY.line_spacing,
    high_contrast: Boolean(merged.high_contrast),
    focus_isolation: Boolean(merged.focus_isolation),
  };
}

export function applyAccessibility(settings) {
  const resolved = resolveAccessibility(settings);
  const root = document.documentElement;

  root.style.setProperty("--font-sans", FONT_CHOICES[resolved.font].stack);
  root.style.lineHeight = String(LINE_SPACING_CHOICES[resolved.line_spacing].value);

  if (resolved.high_contrast) {
    root.setAttribute("data-contrast", "high");
  } else {
    root.removeAttribute("data-contrast");
  }

  // Focus isolation dims everything except the section being read. Module 3's
  // own finding is that looking away from the text is read as disengagement,
  // so reducing what competes for attention is a sensing benefit as well as a
  // comfort one. The actual dimming is done in CSS by the reading screen.
  if (resolved.focus_isolation) {
    root.setAttribute("data-focus-isolation", "on");
  } else {
    root.removeAttribute("data-focus-isolation");
  }

  return resolved;
}

/**
 * Apply the profile's settings, falling back to whatever was last seen.
 *
 * Deliberately does NOT apply the defaults while `profile` is still loading:
 * that would flash the default theme over a learner's high-contrast one on
 * every page load. The stored copy covers that window instead.
 */
export function useAccessibility(profile) {
  useEffect(() => {
    const fromProfile = profile?.accessibility_settings;
    if (fromProfile) {
      const resolved = applyAccessibility(fromProfile);
      storeAccessibility(resolved);
      return;
    }
    applyAccessibility(readStoredAccessibility() ?? DEFAULT_ACCESSIBILITY);
  }, [profile]);
}

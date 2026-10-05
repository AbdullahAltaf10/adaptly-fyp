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
 * The two fonts the shared contract allows.
 *
 * `shared/contracts/user-profile.schema.json` says `font` is exactly
 * `"default"` or `"opendyslexic"`, and scope 4.1 names OpenDyslexic. This file
 * used to offer four system stacks with names the contract has never had
 * ("sans", "serif", "mono"), so every save wrote a value the contract rejects
 * and the font the scope promised was not offered at all.
 *
 * OpenDyslexic is bundled (`@fontsource/opendyslexic`, OFL) rather than loaded
 * from a CDN, so it works offline and nothing about a learner's reading needs
 * a third party. It is fetched only when somebody actually chooses it - see
 * `loadFont` - so everyone else pays nothing for it, and until it arrives the
 * stack falls back to a system font rather than showing nothing.
 */
export const FONT_CHOICES = {
  default: { label: "System default", stack: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
  opendyslexic: {
    label: "OpenDyslexic",
    stack: '"OpenDyslexic", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  },
};

/** Names an older build stored. Mapped rather than discarded, so nobody's choice resets. */
const LEGACY_FONTS = { system: "default", sans: "default", serif: "default", mono: "default" };

/**
 * The contract stores line spacing as a NUMBER between 1 and 3, not a name.
 * These are presets over that range; any number inside it is still valid.
 */
export const MIN_LINE_SPACING = 1;
export const MAX_LINE_SPACING = 3;

export const LINE_SPACING_CHOICES = [
  { value: 1.3, label: "Compact" },
  { value: 1.5, label: "Normal" },
  { value: 1.9, label: "Relaxed" },
  { value: 2.2, label: "Loose" },
];

/** Names an older build stored. Same reasoning as LEGACY_FONTS. */
const LEGACY_LINE_SPACING = { compact: 1.3, normal: 1.5, relaxed: 1.9, loose: 2.2 };

// 1.5 matches the default the backend writes for a new profile
// (`users/models.py`), so an untouched profile and an unsaved one agree.
export const DEFAULT_ACCESSIBILITY = {
  font: "default",
  line_spacing: 1.5,
  high_contrast: false,
  focus_isolation: false,
};

function resolveFont(value) {
  if (FONT_CHOICES[value]) return value;
  return LEGACY_FONTS[value] ?? DEFAULT_ACCESSIBILITY.font;
}

function resolveLineSpacing(value) {
  const numeric = typeof value === "string" && value in LEGACY_LINE_SPACING
    ? LEGACY_LINE_SPACING[value]
    : value;
  if (typeof numeric !== "number" || !Number.isFinite(numeric)) {
    return DEFAULT_ACCESSIBILITY.line_spacing;
  }
  // Clamped rather than rejected: a value outside the range is a mistake to
  // repair, not a reason to throw the learner's whole configuration away.
  return Math.min(MAX_LINE_SPACING, Math.max(MIN_LINE_SPACING, numeric));
}

let openDyslexicRequested = false;

/** Fetch OpenDyslexic once, the first time somebody chooses it. */
function loadFont(font) {
  if (font !== "opendyslexic" || openDyslexicRequested) return;
  openDyslexicRequested = true;
  import("@fontsource/opendyslexic/latin-400.css").catch(() => {
    // Not being able to load the font must not break reading: the stack has a
    // system fallback. Allow another attempt on the next apply.
    openDyslexicRequested = false;
  });
}

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
    font: resolveFont(merged.font),
    line_spacing: resolveLineSpacing(merged.line_spacing),
    high_contrast: Boolean(merged.high_contrast),
    focus_isolation: Boolean(merged.focus_isolation),
  };
}

export function applyAccessibility(settings) {
  const resolved = resolveAccessibility(settings);
  const root = document.documentElement;

  loadFont(resolved.font);
  root.style.setProperty("--font-sans", FONT_CHOICES[resolved.font].stack);
  root.style.lineHeight = String(resolved.line_spacing);

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

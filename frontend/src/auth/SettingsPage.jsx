/**
 * Accessibility settings — the screen that makes scope 6.1's promise true.
 *
 * "Accessibility settings such as font choice, line spacing, and contrast are
 * saved to any profile type and applied automatically at the start of every
 * session." The backend has stored these since Module 1; nothing read them
 * back, and the one place that tried read the wrong key (see
 * `useAccessibility.js`).
 *
 * The important detail is that **changes preview immediately**, before saving.
 * Someone choosing a line spacing because reading is hard cannot evaluate it
 * from the name "Relaxed" — they have to see it. So every change applies to
 * the document at once, and Save persists it. Leaving without saving restores
 * what was stored, so a preview is never mistaken for a commitment.
 */

import { AlignJustify, Contrast, Focus, Type } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "./AuthContext";
import SecuritySettings from "./SecuritySettings";
import {
  DEFAULT_ACCESSIBILITY,
  FONT_CHOICES,
  LINE_SPACING_CHOICES,
  applyAccessibility,
  resolveAccessibility,
} from "./useAccessibility";
import api from "../api/client";
import { Alert, Button, Card, Field, Select } from "../ui";

export default function SettingsPage() {
  const navigate = useNavigate();
  const { profile, refreshProfile } = useAuth();

  const saved = resolveAccessibility(profile?.accessibility_settings ?? DEFAULT_ACCESSIBILITY);
  const [draft, setDraft] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);

  // Preview as they go.
  useEffect(() => {
    applyAccessibility(draft);
  }, [draft]);

  // If they navigate away without saving, put the document back.
  useEffect(() => {
    return () => {
      applyAccessibility(profile?.accessibility_settings ?? DEFAULT_ACCESSIBILITY);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = (key, value) => setDraft((current) => ({ ...current, [key]: value }));

  const handleSave = async (event) => {
    event.preventDefault();
    setStatus(null);
    setBusy(true);
    try {
      await api.put("/users/me", { accessibility_settings: draft });
      await refreshProfile();
      setStatus({ tone: "success", message: "Saved. These apply from your next session onwards." });
    } catch (error) {
      setStatus({
        tone: "error",
        message: error?.message || "Could not save your settings. Try again.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <Card
        title="Reading and accessibility"
        subtitle="Changes preview as you make them. Nothing is kept until you save."
      >
        {status && <Alert tone={status.tone}>{status.message}</Alert>}

        <form onSubmit={handleSave} noValidate>
          <Field
            label={
              <span className="inline-flex items-center gap-1.5">
                <Type size={15} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                Font
              </span>
            }
            hint="OpenDyslexic has weighted letter bottoms that make letters harder to flip. It downloads once, only if you choose it."
          >
            {(aria) => (
              <Select
                {...aria}
                value={draft.font}
                onChange={(e) => update("font", e.target.value)}
              >
                {Object.entries(FONT_CHOICES).map(([value, { label }]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          <Field
            label={
              <span className="inline-flex items-center gap-1.5">
                <AlignJustify size={15} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                Line spacing
              </span>
            }
            hint="More space between lines helps if text runs together."
          >
            {(aria) => (
              <Select
                {...aria}
                value={String(draft.line_spacing)}
                // The contract stores a number, and <select> hands back a string.
                onChange={(e) => update("line_spacing", Number(e.target.value))}
              >
                {LINE_SPACING_CHOICES.map(({ value, label }) => (
                  <option key={value} value={String(value)}>
                    {label}
                  </option>
                ))}
                {/* A number set elsewhere, inside the contract's range but not
                    one of the presets, still has to show as what it is. */}
                {!LINE_SPACING_CHOICES.some(({ value }) => value === draft.line_spacing) && (
                  <option value={String(draft.line_spacing)}>Custom ({draft.line_spacing})</option>
                )}
              </Select>
            )}
          </Field>

          <fieldset className="border-0 p-0 m-0 mb-4">
            <legend className="font-medium mb-2">Display</legend>

            <label className="flex items-start gap-3 mb-3 cursor-pointer">
              <input
                type="checkbox"
                className="mt-1"
                checked={draft.high_contrast}
                onChange={(e) => update("high_contrast", e.target.checked)}
              />
              <span>
                <span className="flex items-center gap-1.5 font-medium">
                  <Contrast size={15} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                  High contrast
                </span>
                <span className="block text-sm text-muted">
                  Maximum separation between text and background.
                </span>
              </span>
            </label>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                className="mt-1"
                checked={draft.focus_isolation}
                onChange={(e) => update("focus_isolation", e.target.checked)}
              />
              <span>
                <span className="flex items-center gap-1.5 font-medium">
                  <Focus size={15} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                  Focus isolation
                </span>
                <span className="block text-sm text-muted">
                  Dim everything except the section you are reading.
                </span>
              </span>
            </label>
          </fieldset>

          <p className="text-muted mb-4">
            The quick brown fox jumps over the lazy dog. This paragraph uses the settings above, so
            you can see what reading will feel like before you commit to them.
          </p>

          <div className="flex gap-2">
            <Button type="submit" busy={busy} busyLabel="Saving...">
              Save settings
            </Button>
            <Button type="button" variant="secondary" onClick={() => setDraft(saved)}>
              Reset
            </Button>
            <Button type="button" variant="quiet" onClick={() => navigate(-1)}>
              Back
            </Button>
          </div>
        </form>
      </Card>

      <SecuritySettings />
    </div>
  );
}

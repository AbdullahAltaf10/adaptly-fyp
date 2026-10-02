/**
 * Scope 6.8: "No statistics, scores, or indicators are shown during an
 * active session."
 *
 * The reported engagement state (Focused/Drifting/Struggling/...) used to
 * render unconditionally, in colour, right under the video - exactly the
 * indicator this rule forbids. It now lives only inside the collapsed
 * Diagnostics `<details>`, a development instrument a learner never opens by
 * accident. This test is what keeps it from quietly coming back.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const baseCapture = {
  videoRef: { current: null },
  ready: true,
  calibrated: true,
  calibrating: false,
  calibrationError: null,
  runCalibration: vi.fn(),
  faceDetected: true,
  status: "Ready",
  framesCollected: 10,
  windowSize: 10,
  lightingWarning: null,
  droppedWindows: 0,
  sessionId: "live-session-123",
  endSessionNow: () => Promise.resolve({}),
  prediction: {
    state: "struggling",
    confidence: 0.82,
    diagnostics: { smoothing: { raw_state: "struggling", stable: true, streak: 3, required: 3 } },
  },
};

vi.mock("../engagement/useEngagementCapture", () => ({
  useEngagementCapture: () => baseCapture,
}));
vi.mock("../engagement/useFacePresence", () => ({
  useFacePresence: () => ({
    faceLost: false,
    showTick: false,
    suggestRecalibrate: false,
    dismissRecalibrate: vi.fn(),
  }),
}));
vi.mock("../intervention/useDwell", () => ({
  useDwell: () => ({ seconds: () => 0, register: vi.fn(), visibilityRatios: () => new Map() }),
}));
vi.mock("../intervention/useIntervention", () => ({
  useIntervention: () => ({
    current: null,
    content: null,
    loading: false,
    accepted: false,
    accept: vi.fn(),
    complete: vi.fn(),
    dismiss: vi.fn(),
  }),
}));
vi.mock("../content/useContent", () => ({
  useContent: () => ({ content: null, loading: false, error: null }),
}));
vi.mock("../engagement/usePreSessionCheck", () => ({
  CAMERA_UNKNOWN: "unknown",
  CAMERA_OK: "ok",
  CAMERA_DENIED: "denied",
  CAMERA_MISSING: "missing",
  CAMERA_FAILED: "failed",
  usePreSessionCheck: () => ({
    videoRef: { current: null },
    checking: false,
    camera: "ok",
    cameraReady: true,
    brightness: 120,
    lowLight: false,
    recheck: vi.fn(),
  }),
}));
vi.mock("../features/ai-assistant/AssistantPanel", () => ({
  AssistantPanel: () => null,
}));

import StudySession from "./StudySession";

function draw() {
  return render(
    <MemoryRouter>
      <StudySession contentId="content-1" chunkId="chunk-1" />
    </MemoryRouter>
  );
}

/**
 * Whether `pattern` appears as text anywhere outside the collapsed
 * Diagnostics `<details>`. Its content is present in the DOM either way -
 * `<details>` without `open` hides it visually, not from the document - so
 * the check that matters is containment, not presence.
 */
function matchesOutsideDiagnostics(container, pattern) {
  const details = container.querySelector("details:not([open])");
  expect(details).toBeTruthy();

  return Array.from(container.querySelectorAll("*"))
    .filter((el) => el !== details && !details.contains(el) && !el.contains(details))
    .some((el) => el.children.length === 0 && pattern.test(el.textContent ?? ""));
}

describe("scope 6.8: no state, score, or indicator visible to the learner", () => {
  it("never shows the reported state label outside the collapsed diagnostics", () => {
    const { container } = draw();
    fireEventStart();

    const details = container.querySelector("details:not([open])");
    expect(details.textContent).toMatch(/struggling/i); // Diagnostics does render it, just there

    expect(matchesOutsideDiagnostics(container, /struggling/i)).toBe(false);
  });

  it("never shows a confidence percentage outside the collapsed diagnostics", () => {
    const { container } = draw();
    fireEventStart();

    const details = container.querySelector("details:not([open])");
    expect(details.textContent).toMatch(/82(\.0)?%/); // present, just inside diagnostics

    expect(matchesOutsideDiagnostics(container, /82(\.0)?%/)).toBe(false);
  });
});

function fireEventStart() {
  // eslint-disable-next-line testing-library/no-node-access -- the Start
  // session button belongs to PreSessionCheck, mocked minimally above via
  // its hook only, so the real component renders its real button.
  const button = screen.getByRole("button", { name: /start session/i });
  button.click();
}

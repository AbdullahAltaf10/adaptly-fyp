/**
 * "End session" - the control this screen was entirely missing.
 *
 * Before this, a session only ever ended when the whole page unmounted:
 * navigating elsewhere in the SPA (which still worked, via the capture hook's
 * effect cleanup) or closing the tab (which did not - React never gets to run
 * cleanup on a closed tab, so the backend never learned the session had
 * ended, and it produced no analytics summary, no insight report, and for a
 * corporate account no compliance report - all three only ever run at
 * session end). A learner who simply left the tab open, or closed it instead
 * of navigating away, generated nothing.
 *
 * These tests cover the deliberate path: clicking "End session" must await
 * the real backend call before it sends the learner anywhere, so they land on
 * analytics that have actually been computed rather than a page that is
 * empty because finalization is still in flight.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navigateSpy = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => navigateSpy };
});

let endSessionNow;

const baseCapture = {
  videoRef: { current: null },
  ready: true,
  calibrated: false,
  calibrating: false,
  calibrationError: null,
  runCalibration: vi.fn(),
  faceDetected: false,
  status: "Ready",
  framesCollected: 0,
  windowSize: 10,
  lightingWarning: null,
  droppedWindows: 0,
  prediction: null,
  sessionId: "live-session-123",
  get endSessionNow() {
    return endSessionNow;
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

function startSession() {
  fireEvent.click(screen.getByRole("button", { name: /start session/i }));
}

beforeEach(() => {
  navigateSpy.mockReset();
  endSessionNow = vi.fn().mockResolvedValue({});
});

describe("StudySession — ending a session", () => {
  it("offers no way to end a session before one has started", () => {
    draw();

    expect(screen.queryByRole("button", { name: /end session/i })).not.toBeInTheDocument();
  });

  it("offers 'End session' once one has started", () => {
    draw();
    startSession();

    expect(screen.getByRole("button", { name: /end session/i })).toBeInTheDocument();
  });

  it("calls the real backend end-session, not just a local state flip", async () => {
    draw();
    startSession();

    fireEvent.click(screen.getByRole("button", { name: /end session/i }));

    await waitFor(() => expect(endSessionNow).toHaveBeenCalledTimes(1));
  });

  it("navigates to that session's own analytics after the backend acknowledges", async () => {
    draw();
    startSession();

    fireEvent.click(screen.getByRole("button", { name: /end session/i }));

    await waitFor(() =>
      expect(navigateSpy).toHaveBeenCalledWith("/analytics?session=live-session-123")
    );
  });

  it("still navigates the learner onward even if the backend call fails", async () => {
    endSessionNow = vi.fn().mockRejectedValue(new Error("network blip"));
    draw();
    startSession();

    fireEvent.click(screen.getByRole("button", { name: /end session/i }));

    await waitFor(() => expect(navigateSpy).toHaveBeenCalled());
  });

  it("shows a busy state and does not double-submit while ending", async () => {
    let resolveEnd;
    endSessionNow = vi.fn(() => new Promise((resolve) => { resolveEnd = resolve; }));
    draw();
    startSession();

    const button = screen.getByRole("button", { name: /end session/i });
    fireEvent.click(button);

    expect(await screen.findByRole("button", { name: /ending session/i })).toBeDisabled();
    fireEvent.click(button);
    expect(endSessionNow).toHaveBeenCalledTimes(1);

    resolveEnd({});
    await waitFor(() => expect(navigateSpy).toHaveBeenCalled());
  });
});

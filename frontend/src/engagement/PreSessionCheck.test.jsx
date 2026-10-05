/**
 * Scope 6.2 asks for a check, and the thing that makes it a check rather than
 * a notice is that it changes what the learner can do.
 *
 * So these tests are about the two decisions: a missing camera stops the
 * session, and low light does not. Getting the second one backwards would be
 * easy and would quietly lock people out of studying at night, which is not
 * ours to decide.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PreSessionCheck from "./PreSessionCheck";
import {
  CAMERA_DENIED,
  CAMERA_FAILED,
  CAMERA_MISSING,
  CAMERA_OK,
} from "./usePreSessionCheck";

function checkState(overrides = {}) {
  return {
    videoRef: { current: null },
    checking: false,
    camera: CAMERA_OK,
    cameraReady: true,
    brightness: 120,
    lowLight: false,
    recheck: vi.fn(),
    ...overrides,
  };
}

function setup(overrides = {}, props = {}) {
  return render(
    <PreSessionCheck
      check={checkState(overrides)}
      onStart={vi.fn()}
      panelStyle={{}}
      {...props}
    />
  );
}

const startButton = () => screen.getByRole("button", { name: /start session/i });

describe("what blocks a session and what does not", () => {
  it("lets the learner start when the camera works", () => {
    setup();
    expect(startButton().disabled).toBe(false);
  });

  it.each([
    [CAMERA_DENIED, /blocked/i],
    [CAMERA_MISSING, /no camera was found/i],
    [CAMERA_FAILED, /could not be started/i],
  ])("blocks the session when the camera is %s, and says why", (camera, message) => {
    setup({ camera, cameraReady: false, brightness: null, lowLight: null });

    expect(startButton().disabled).toBe(true);
    expect(screen.getByText(message)).toBeTruthy();
    // The three failures need different things done about them, so they must
    // not collapse into one generic message.
    expect(screen.getByRole("button", { name: /check again/i })).toBeTruthy();
  });

  it("does NOT block the session in low light", () => {
    // Detection degrades, it does not stop. Someone studying in a dim room at
    // night has made a reasonable choice.
    setup({ brightness: 20, lowLight: true });

    expect(startButton().disabled).toBe(false);
    expect(screen.getByText(/lighting is low/i)).toBeTruthy();
    expect(screen.getByText(/you can still start/i)).toBeTruthy();
  });

  it("treats unmeasured lighting as unmeasured, not as adequate", () => {
    setup({ brightness: null, lowLight: null });

    expect(screen.getByText(/could not be measured/i)).toBeTruthy();
    expect(screen.queryByText(/lighting looks fine/i)).toBeNull();
    expect(startButton().disabled).toBe(false);
  });

  it("cannot be started while the check is still running", () => {
    setup({ checking: true, cameraReady: false, camera: "unknown" });
    expect(startButton().disabled).toBe(true);
    expect(screen.getByText(/checking your camera/i)).toBeTruthy();
  });
});

describe("Module 2's document warnings", () => {
  it("shows a known warning in words the learner can act on", () => {
    setup({}, { warnings: ["urdu_content_reduced_accuracy"] });

    const text = screen.getByText(/this document is in urdu/i);
    expect(text).toBeTruthy();
    // The code itself is a classification, not something to show a learner.
    expect(text.textContent).not.toMatch(/urdu_content_reduced_accuracy/);
  });

  it("shows an unrecognised warning rather than swallowing it", () => {
    // Module 2 can add a code without this file knowing. Dropping it would
    // mean a warning that was deliberately raised never reaches anyone.
    setup({}, { warnings: ["some_future_code"] });
    expect(screen.getByText(/some_future_code/)).toBeTruthy();
  });

  it("shows every warning, not just the first", () => {
    setup({}, {
      warnings: ["urdu_content_reduced_accuracy", "low_confidence_transcription"],
    });
    expect(screen.getByText(/this document is in urdu/i)).toBeTruthy();
    expect(screen.getByText(/automatic transcription/i)).toBeTruthy();
  });

  it("says nothing about the document when there is nothing to say", () => {
    setup({}, { warnings: [] });
    expect(screen.queryByText(/about this document/i)).toBeNull();
  });
});

describe("WebGazer calibration and readability suggestion", () => {
  it("shows a skippable 'calibrate your eyes' step once the camera is ready", () => {
    // "calibrate" alone would also match the button's own label ("Calibrate"),
    // so this checks the descriptive copy specifically, not just any match.
    setup({ webgazerStatus: "idle" });
    expect(screen.getByText(/eye tracking/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /skip/i })).toBeInTheDocument();
  });

  it("does not block Start while calibration is unavailable", () => {
    setup({ webgazerStatus: "unavailable" });
    expect(screen.getByRole("button", { name: /start session/i })).not.toBeDisabled();
  });

  it("shows a dismissible font/line-spacing suggestion when one is present", () => {
    const dismissReadabilitySuggestion = vi.fn();
    setup({
      webgazerStatus: "ready",
      readabilitySuggestion: { fontUp: true, lineSpacingUp: false },
      dismissReadabilitySuggestion,
    });
    expect(screen.getByText(/larger text might make this easier/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(dismissReadabilitySuggestion).toHaveBeenCalled();
  });

  it("never renders a suggestion when readabilitySuggestion is null", () => {
    setup({ webgazerStatus: "ready", readabilitySuggestion: null });
    expect(screen.queryByText(/larger text/i)).not.toBeInTheDocument();
  });

  it("shows a click target for every calibration point while awaiting clicks, not a single button that silently claims readiness", () => {
    setup({
      webgazerStatus: "awaiting-points",
      calibrationPointsClicked: new Set(),
    });
    // One real click target per CALIBRATION_POINTS entry (5), each its own
    // accessible button - the bug this replaces was a single "Calibrate"
    // click flipping straight to "ready" with zero training samples given
    // to WebGazer's regression.
    expect(screen.getAllByRole("button", { name: /calibration point/i })).toHaveLength(5);
  });

  it("calls recordCalibrationPoint with the clicked point's index", () => {
    const recordCalibrationPoint = vi.fn();
    setup({
      webgazerStatus: "awaiting-points",
      calibrationPointsClicked: new Set(),
      recordCalibrationPoint,
    });
    fireEvent.click(screen.getAllByRole("button", { name: /calibration point/i })[2]);
    expect(recordCalibrationPoint).toHaveBeenCalledWith(2);
  });

  it("marks an already-clicked point so the learner can see their progress", () => {
    setup({
      webgazerStatus: "awaiting-points",
      calibrationPointsClicked: new Set([0, 1]),
    });
    const buttons = screen.getAllByRole("button", { name: /calibration point/i });
    expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
    expect(buttons[2].getAttribute("aria-pressed")).toBe("false");
  });

  it("stops showing calibration points once status reaches ready", () => {
    setup({ webgazerStatus: "ready", calibrationPointsClicked: new Set() });
    expect(screen.queryByRole("button", { name: /calibration point/i })).not.toBeInTheDocument();
  });
});

describe("privacy copy", () => {
  it("states that no video leaves the browser", () => {
    setup();
    expect(
      screen.getByText(/no video is recorded, stored, or sent anywhere/i)
    ).toBeTruthy();
  });
});

describe("the document this session is about", () => {
  it("blocks Start while the document is still loading", () => {
    // Otherwise a learner who chose a document and hit Start quickly gets a
    // session with nothing to read.
    setup({}, { document: { loading: true, error: null } });
    expect(startButton().disabled).toBe(true);
    expect(screen.getByText(/loading your document/i)).toBeTruthy();
  });

  it("blocks Start and says why when the document could not be opened", () => {
    // The error used to sit behind this dialog where nobody could see it, and
    // Start stayed enabled - so a learner who picked a document that no longer
    // existed started a session with nothing to read and no explanation.
    setup({}, { document: { loading: false, error: "Content not found" } });
    expect(startButton().disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toMatch(/could not be opened/i);
    expect(screen.getByRole("link", { name: /choose another document/i }).getAttribute("href")).toBe(
      "/library"
    );
  });

  it("lets a camera-only session start, with no document to wait for", () => {
    setup({}, { document: undefined });
    expect(startButton().disabled).toBe(false);
  });

  it("lets Start through once the document has loaded", () => {
    setup({}, { document: { loading: false, error: null } });
    expect(startButton().disabled).toBe(false);
  });

  it("still blocks on a missing camera even when the document is fine", () => {
    setup(
      { camera: CAMERA_DENIED, cameraReady: false, brightness: null, lowLight: null },
      { document: { loading: false, error: null } }
    );
    expect(startButton().disabled).toBe(true);
  });
});

/**
 * Scope 6.2 asks for a check, and the thing that makes it a check rather than
 * a notice is that it changes what the learner can do.
 *
 * So these tests are about the two decisions: a missing camera stops the
 * session, and low light does not. Getting the second one backwards would be
 * easy and would quietly lock people out of studying at night, which is not
 * ours to decide.
 */

import { render, screen } from "@testing-library/react";
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

describe("privacy copy", () => {
  it("states that no video leaves the browser", () => {
    setup();
    expect(
      screen.getByText(/no video is recorded, stored, or sent anywhere/i)
    ).toBeTruthy();
  });
});

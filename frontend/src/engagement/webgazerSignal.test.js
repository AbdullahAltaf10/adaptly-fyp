// frontend/src/engagement/webgazerSignal.test.js
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let storedGazeListener = null;
let beginResult = Promise.resolve();
let endCalled = false;

let saveDataAcrossSessionsCalledWith = null;
let stopVideoCalled = false;
let clearDataCalled = false;

const webgazerMock = {
  setRegression: vi.fn(() => webgazerMock),
  setGazeListener: vi.fn((callback) => {
    storedGazeListener = callback;
    return webgazerMock;
  }),
  showVideo: vi.fn(() => webgazerMock),
  showFaceOverlay: vi.fn(() => webgazerMock),
  showFaceFeedbackBox: vi.fn(() => webgazerMock),
  showPredictionPoints: vi.fn(() => webgazerMock),
  saveDataAcrossSessions: vi.fn((val) => {
    saveDataAcrossSessionsCalledWith = val;
    return webgazerMock;
  }),
  begin: vi.fn(() => beginResult),
  end: vi.fn(() => { endCalled = true; }),
  stopVideo: vi.fn(() => { stopVideoCalled = true; }),
  clearData: vi.fn(() => { clearDataCalled = true; return Promise.resolve(); }),
};

vi.mock("webgazer", () => ({ default: webgazerMock }));

beforeEach(async () => {
  vi.resetModules();
  storedGazeListener = null;
  beginResult = Promise.resolve();
  endCalled = false;
  saveDataAcrossSessionsCalledWith = null;
  stopVideoCalled = false;
  clearDataCalled = false;
});

describe("webgazerSignal", () => {
  it("reports unavailable before calibration has ever run", async () => {
    const { getWebgazerSignal } = await import("./webgazerSignal");
    expect(getWebgazerSignal()).toBeNull();
  });

  it("starts reporting gaze points once calibration resolves and the listener fires", async () => {
    const { calibrateWebgazer, getWebgazerSignal } = await import("./webgazerSignal");
    const result = await calibrateWebgazer();
    expect(result.available).toBe(true);
    storedGazeListener({ x: 640, y: 200 });
    expect(getWebgazerSignal()).toEqual({ x: 640, y: 200, confidence: 1.0 });
  });

  it("ignores a null gaze event without throwing", async () => {
    const { calibrateWebgazer, getWebgazerSignal } = await import("./webgazerSignal");
    await calibrateWebgazer();
    storedGazeListener(null);
    expect(getWebgazerSignal()).toBeNull();
  });

  it("resolves available:false, never rejects, when begin() throws", async () => {
    beginResult = Promise.reject(new Error("camera permission denied"));
    // Attaching a second, no-op handler here only silences the test
    // runner's unhandled-rejection warning for this deliberately-rejected
    // promise; production code below still awaits and catches the same
    // `beginResult` reference via `begin: vi.fn(() => beginResult)`.
    beginResult.catch(() => {});
    const { calibrateWebgazer, getWebgazerSignal } = await import("./webgazerSignal");
    const result = await calibrateWebgazer();
    expect(result).toEqual({ available: false, reason: "camera permission denied" });
    expect(getWebgazerSignal()).toBeNull();
  });

  it("stopWebgazer clears the last known prediction and calls webgazer.end()", async () => {
    const { calibrateWebgazer, getWebgazerSignal, stopWebgazer } = await import("./webgazerSignal");
    await calibrateWebgazer();
    storedGazeListener({ x: 1, y: 1 });
    stopWebgazer();
    await Promise.resolve(); // let the .then() in stopWebgazer run
    expect(getWebgazerSignal()).toBeNull();
    expect(endCalled).toBe(true);
  });

  it("disables cross-session data persistence before starting, so no eye-patch images are written to IndexedDB", async () => {
    // WebGazer defaults to saveDataAcrossSessions: true, which writes cropped
    // eye-region images to IndexedDB on every click - flatly contradicting
    // docs/privacy/webcam-data-handling.md and the pre-session dialog's own
    // "no video is recorded, stored, or sent anywhere" promise.
    const { calibrateWebgazer } = await import("./webgazerSignal");
    await calibrateWebgazer();
    expect(saveDataAcrossSessionsCalledWith).toBe(false);
  });

  it("stopWebgazer actually stops the camera and clears any stored eye-tracking data", async () => {
    // The installed WebGazer's own end() leaves stopVideo() commented out -
    // the camera keeps streaming after a session ends unless this module
    // stops it itself.
    const { calibrateWebgazer, stopWebgazer } = await import("./webgazerSignal");
    await calibrateWebgazer();
    stopWebgazer();
    await Promise.resolve();
    expect(stopVideoCalled).toBe(true);
    expect(clearDataCalled).toBe(true);
  });

  it("stopWebgazer is a safe no-op when calibration never ran", async () => {
    const { stopWebgazer } = await import("./webgazerSignal");
    expect(() => stopWebgazer()).not.toThrow();
  });
});

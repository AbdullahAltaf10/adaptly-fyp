// frontend/src/engagement/webgazerSignal.js
/**
 * Wraps the `webgazer` package behind the same shape as the other fusion
 * signals, and lazy-loads it - a study page that never runs a session never
 * pays for the WebGazer bundle.
 *
 * WebGazer calibrates itself from click interactions (Papoutsaki et al.,
 * scope ref [18]) - its estimate is only trustworthy after calibrateWebgazer()
 * resolves `available: true`. Before that, or if the browser/camera refuses
 * it, this reports null and fusion falls back to the other three signals -
 * same warn-don't-block posture as every other pre-session check in this
 * codebase.
 *
 * Two things WebGazer does by default that this module must override, found
 * during code review by reading its own source (node_modules/webgazer):
 * it defaults `saveDataAcrossSessions` to true, writing cropped eye-region
 * images to IndexedDB on every click, and its own `end()` leaves
 * `stopVideo()` commented out, so the camera keeps streaming after a
 * session ends. Both directly contradict this project's own privacy
 * guarantees (docs/privacy/webcam-data-handling.md, and the pre-session
 * dialog's "no video is recorded, stored, or sent anywhere"), so both are
 * corrected explicitly below rather than left at WebGazer's defaults.
 */

let webgazerModulePromise = null;
let latestPrediction = null;

function loadWebgazer() {
  if (!webgazerModulePromise) {
    webgazerModulePromise = import("webgazer").then((module) => module.default ?? module);
  }
  return webgazerModulePromise;
}

export async function calibrateWebgazer() {
  try {
    const webgazer = await loadWebgazer();
    webgazer.setGazeListener((data) => {
      latestPrediction = data ? { x: data.x, y: data.y } : null;
    });
    webgazer
      .showVideo(false)
      .showFaceOverlay(false)
      .showFaceFeedbackBox(false)
      .showPredictionPoints(false)
      .saveDataAcrossSessions(false);
    await webgazer.setRegression("ridge").begin();
    return { available: true };
  } catch (error) {
    latestPrediction = null;
    return { available: false, reason: error?.message ?? String(error) };
  }
}

const WEBGAZER_CONFIDENCE = 1.0;

/** Reads WebGazer's latest gaze estimate, or null before calibration / this tick. */
export function getWebgazerSignal() {
  if (!latestPrediction) return null;
  return { x: latestPrediction.x, y: latestPrediction.y, confidence: WEBGAZER_CONFIDENCE };
}

export function stopWebgazer() {
  latestPrediction = null;
  if (!webgazerModulePromise) return;
  webgazerModulePromise
    .then((webgazer) => {
      webgazer.end();
      // webgazer.end() does not stop the camera track (see module docstring)
      // and does not clear whatever it wrote to IndexedDB this session.
      webgazer.stopVideo?.();
      return webgazer.clearData?.();
    })
    .catch(() => {});
}

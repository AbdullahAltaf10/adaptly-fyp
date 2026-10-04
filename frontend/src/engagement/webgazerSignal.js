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
 *
 * A third thing, found the same way, used to be missing entirely rather
 * than overridden: `addMouseEventListeners()` is a public WebGazer method,
 * never called anywhere inside the library itself (confirmed by searching
 * the whole bundle), that attaches the click/mousemove listener its ridge
 * regression actually trains from. Without calling it, `begin()` still
 * starts the gaze listener firing every tick, but from a regression that
 * has never seen a single training sample - every (x, y) WebGazer ever
 * reported was noise from an untrained model, regardless of what the UI
 * told the learner. See calibrationDots.js for the explicit click sequence
 * that gives it real training data before a session starts, on top of
 * whatever incidental clicks happen during the session itself.
 */

let webgazerModulePromise = null;
let latestPrediction = null;

/**
 * Where the explicit click-calibration sequence places its targets
 * (fractions of viewport width/height), consumed by usePreSessionCheck.js's
 * recordCalibrationPoint flow and rendered by PreSessionCheck.jsx. Four
 * corners plus one off-centre point, all chosen to sit outside the
 * pre-session dialog's own centred card so neither obscures the other.
 * Five points, not one: a single click only ever gives WebGazer one (x, y)
 * sample, nowhere near enough for ridge regression to fit a usable mapping
 * across the whole screen.
 */
export const CALIBRATION_POINTS = [
  { x: 0.08, y: 0.08 },
  { x: 0.92, y: 0.08 },
  { x: 0.08, y: 0.92 },
  { x: 0.92, y: 0.92 },
  { x: 0.5, y: 0.04 },
];

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
    webgazer.addMouseEventListeners();
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

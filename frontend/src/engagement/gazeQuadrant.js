// frontend/src/engagement/gazeQuadrant.js
/**
 * A coarse, free "which vertical band of the viewport is the eye pointed
 * at" heuristic - the S2 fusion signal.
 *
 * Reuses the exact same iris-offset calculation ml/inference/features.py
 * uses for gaze_y (mean iris position minus mean eye position, per eye,
 * averaged) - not a new landmark formula, just computed here client-side,
 * once per capture tick, instead of waiting on a server round-trip.
 *
 * Deliberately coarse: the scope document states webcam gaze accuracy at
 * 2-3cm on screen, so this can only ever mean "roughly top/middle/bottom
 * third" - never a precise point. fusionScoring.js's low SIGNAL_WEIGHTS.gazeQuadrant
 * reflects that; this module's own confidence stays fixed at 1.0 because the
 * coarseness lives in the weight, not here.
 *
 * Thresholds are the trained scaler's own measured population mean/std for
 * gaze_y (ml/artifacts/MANIFEST.json, mirrored in
 * sibtain-workspace/FYP_DEFENSE_GUIDE/13_NUMBERS_CHEATSHEET.md) - reused so
 * the band boundaries mean something instead of being arbitrary numbers.
 */

const LEFT_EYE = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];
const LEFT_IRIS = [468, 469, 470, 471];
const RIGHT_IRIS = [473, 474, 475, 476];

const GAZE_Y_MEAN = -0.004969;
const GAZE_Y_STD = 0.001266;

const GAZE_QUADRANT_CONFIDENCE = 1.0;

function averagePoint(landmarks, indices) {
  let x = 0;
  let y = 0;
  for (const index of indices) {
    x += landmarks[index][0];
    y += landmarks[index][1];
  }
  return [x / indices.length, y / indices.length];
}

export function estimateGazeBand(landmarks) {
  if (!landmarks || landmarks.length <= Math.max(...RIGHT_IRIS)) return null;

  const leftIris = averagePoint(landmarks, LEFT_IRIS);
  const rightIris = averagePoint(landmarks, RIGHT_IRIS);
  const leftEye = averagePoint(landmarks, LEFT_EYE);
  const rightEye = averagePoint(landmarks, RIGHT_EYE);

  const gazeY = ((leftIris[1] - leftEye[1]) + (rightIris[1] - rightEye[1])) / 2;

  const band =
    gazeY < GAZE_Y_MEAN - GAZE_Y_STD ? "top" :
    gazeY > GAZE_Y_MEAN + GAZE_Y_STD ? "bottom" :
    "middle";

  return { band, confidence: GAZE_QUADRANT_CONFIDENCE };
}

/**
 * Creating and disposing the MediaPipe FaceLandmarker.
 *
 * The model and WASM runtime are fetched from Google's CDN. Both are pinned to
 * an exact version: an unpinned "latest" would let the landmark model change
 * underneath the LSTM, which was fitted on features derived from this one, and
 * the result would be a quiet accuracy drop rather than a visible failure.
 */

import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

const WASM_PATH =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";

const MODEL_PATH =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/" +
  "face_landmarker/float16/1/face_landmarker.task";

/**
 * Load a FaceLandmarker configured for video.
 *
 * `numFaces: 1` is deliberate. Engagement is reported for the account holder,
 * and picking a face out of several would be a guess. If someone else is in
 * shot, MediaPipe returns whichever face it scores highest, which is a known
 * limitation recorded in the privacy notes.
 */
export async function createFaceLandmarker() {
  const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
  return FaceLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL_PATH, delegate: "GPU" },
    runningMode: "VIDEO",
    numFaces: 1,
  });
}

/**
 * Release a landmarker. Safe to call with null, and safe to call twice.
 *
 * Leaking one holds a GPU context open; React StrictMode mounts effects twice
 * in development, so this runs on a landmarker that may already be gone.
 */
export function closeFaceLandmarker(landmarker) {
  if (!landmarker) return;
  try {
    landmarker.close?.();
  } catch {
    // Already closed, or closed during teardown. Nothing to recover.
  }
}

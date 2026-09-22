/**
 * Turning MediaPipe output into what the backend accepts, and reading the
 * brightness of a frame.
 *
 * Kept free of React so it can be unit tested and reused by any other view
 * that needs the same capture behaviour.
 */

import { LOW_LIGHT_THRESHOLD } from "./constants";

/**
 * Flatten a FaceLandmarker result into `[[x, y, z], ...]`, or null when no
 * face was found.
 *
 * Null is meaningful and must be preserved: it is how the window records
 * "the learner was not visible for this second", which the backend counts
 * when deciding whether a window has enough real data to classify.
 */
export function toLandmarkArray(results) {
  const faces = results?.faceLandmarks;
  if (!faces || faces.length === 0) return null;
  return faces[0].map((p) => [p.x, p.y, p.z]);
}

/** Whether a result contains a face at all. */
export function hasFace(results) {
  return Boolean(results?.faceLandmarks && results.faceLandmarks.length > 0);
}

/**
 * Count the frames in a window that actually contain a face.
 */
export function countValidFrames(window) {
  return window.filter((frame) => frame !== null).length;
}

/**
 * Average brightness of the current video frame, 0-255, or null if the video
 * is not producing pixels yet.
 *
 * The canvas used here is created, read and dropped inside this function. The
 * image is never stored, uploaded, or held in a variable that outlives the
 * call - see docs/privacy/webcam-data-handling.md.
 */
export function averageBrightness(video) {
  if (!video || !video.videoWidth || !video.videoHeight) return null;

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.drawImage(video, 0, 0);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);

  let total = 0;
  for (let i = 0; i < data.length; i += 4) {
    total += (data[i] + data[i + 1] + data[i + 2]) / 3;
  }
  return total / (data.length / 4);
}

/** True when the room is too dark for landmark detection to be reliable. */
export function isLowLight(brightness) {
  return brightness !== null && brightness < LOW_LIGHT_THRESHOLD;
}

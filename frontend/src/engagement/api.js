/**
 * The four engagement endpoints.
 *
 * Wrapped here so the page never builds a request body itself - the shape of
 * `frames` has to match `AnalyzeRequest` on the backend, and a mismatch shows
 * up as a 422 with no useful detail in the UI.
 */

import api from "../api/client";

/**
 * Mark the start of a session.
 *
 * This clears any rule state left over from a previous session using the same
 * id. Without it, a learner who closed the tab and came back inherited the
 * fatigue evidence and confirmation streaks they left behind.
 */
export function startSession(sessionId) {
  return api.post("/engagement/session/start", { session_id: sessionId });
}

/** Mark the end of a session and release its rule state. */
export function endSession(sessionId) {
  return api.post("/engagement/session/end", { session_id: sessionId });
}

/**
 * Send calibration frames and store the learner's baseline.
 *
 * Needed because laptop webcams sit above the screen: looking normally at the
 * screen reads as an extreme downward head angle by the training data's
 * standards, so without a baseline attentive learners are classified as
 * distracted.
 */
export function calibrate(frames) {
  return api.post("/engagement/calibrate", {
    frames: frames.map((landmarks) => ({ landmarks })),
  });
}

/**
 * Send one window for classification.
 *
 * `frames` is an array of `[[x, y, z], ...]` or null entries. Only numbers are
 * sent - no image data ever leaves the browser.
 */
export function analyze(frames, { sessionId, contentId, chunkId } = {}) {
  return api.post("/engagement/analyze", {
    frames: frames.map((landmarks) => ({ landmarks })),
    session_id: sessionId ?? null,
    content_id: contentId ?? null,
    chunk_id: chunkId ?? null,
  });
}

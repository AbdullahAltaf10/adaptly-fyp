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
 *
 * `contentId` is optional and sent only when the caller has one. Module 8's
 * own session record (Issue #82) needs it to be created at all -- without
 * it, the backend safely no-ops instead of writing an invalid record.
 */
export function startSession(sessionId, contentId) {
  return api.post("/engagement/session/start", {
    session_id: sessionId,
    ...(contentId ? { content_id: contentId } : {}),
  });
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
export function analyze(
  frames,
  { sessionId, contentId, chunkId, dwellSeconds } = {}
) {
  return api.post("/engagement/analyze", {
    frames: frames.map((landmarks) => ({ landmarks })),
    session_id: sessionId ?? null,
    content_id: contentId ?? null,
    chunk_id: chunkId ?? null,
    // How long the learner has been on this chunk. Module 4 uses it to decide
    // how intrusive a response is justified - rewriting a paragraph somebody
    // glanced at for three seconds is interference, not support.
    //
    // The browser has to measure it because the server cannot: scrolling
    // produces no request. Until a content viewer exists (issue #12) nothing
    // registers a chunk, this stays 0, and the dwell-gated responses simply
    // never fire. That is the right failure - no dwell evidence, no
    // dwell-based intervention.
    dwell_seconds: dwellSeconds ?? 0,
  });
}

// `is_critical` is deliberately NOT sent. It used to be, and that let a client
// lower its own intervention thresholds by claiming a section mattered. The
// server reads it from the stored chunk now.

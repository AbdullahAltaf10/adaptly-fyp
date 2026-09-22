/**
 * Module 3 capture constants.
 *
 * These were scattered as bare numbers through the prototype's study page.
 * They are gathered here because several of them are load-bearing: the window
 * length and the minimum valid-frame count have to agree with the backend, and
 * silently changing one of them produces wrong predictions rather than an error.
 */

/** Frames per inference window. Must match the model's input shape (10, 9). */
export const WINDOW_SIZE = 10;

/** How often a frame is added to the window. The model was trained on 1 fps. */
export const CAPTURE_INTERVAL_MS = 1000;

/**
 * Minimum frames in a window that must contain a face before it is sent.
 * Below this the window is mostly interpolation, so no prediction is shown
 * rather than a confident-looking guess built from missing data.
 */
export const MIN_VALID_FRAMES = 7;

/** Frames sampled during calibration, and the gap between them. */
export const CALIBRATION_FRAMES = 10;
export const CALIBRATION_INTERVAL_MS = 300;

/**
 * MediaPipe drops the occasional frame even when nobody has moved, so the
 * "move back into frame" overlay waits this long before appearing.
 */
export const FACE_LOST_GRACE_MS = 1500;

/**
 * An absence longer than this suggests the learner got up or changed seat,
 * which makes the calibration baseline stale.
 */
export const RECALIBRATE_SUGGEST_MS = 5000;

/** Average pixel brightness below which a low-light warning is shown. */
export const LOW_LIGHT_THRESHOLD = 60;

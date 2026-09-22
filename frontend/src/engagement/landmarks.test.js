/**
 * Tests for the pure parts of the capture layer.
 *
 * These functions were extracted from the prototype's 630-line study page
 * specifically so they could be tested without a camera, and this file is what
 * makes that claim true rather than aspirational.
 */

import { describe, expect, it } from "vitest";

import {
  countValidFrames,
  hasFace,
  isLowLight,
  toLandmarkArray,
} from "./landmarks";
import {
  CAPTURE_INTERVAL_MS,
  LOW_LIGHT_THRESHOLD,
  MIN_VALID_FRAMES,
  WINDOW_SIZE,
} from "./constants";

/** A MediaPipe-shaped result containing one face of `count` points. */
function resultWithFace(count = 478) {
  return {
    faceLandmarks: [
      Array.from({ length: count }, (_, i) => ({
        x: i / count,
        y: 0.5,
        z: 0.01,
      })),
    ],
  };
}

describe("toLandmarkArray", () => {
  it("flattens a face into [x, y, z] triples", () => {
    const landmarks = toLandmarkArray(resultWithFace(3));
    expect(landmarks).toEqual([
      [0, 0.5, 0.01],
      [1 / 3, 0.5, 0.01],
      [2 / 3, 0.5, 0.01],
    ]);
  });

  it("preserves all 478 points", () => {
    expect(toLandmarkArray(resultWithFace())).toHaveLength(478);
  });

  /**
   * Null is meaningful, not an error. It records "the learner was not visible
   * this second", which is what the backend counts when deciding whether a
   * window has enough real data to classify. Returning [] instead would make
   * an absent face look like a present one with no points.
   */
  it("returns null when no face is present", () => {
    expect(toLandmarkArray({ faceLandmarks: [] })).toBeNull();
    expect(toLandmarkArray({})).toBeNull();
    expect(toLandmarkArray(null)).toBeNull();
    expect(toLandmarkArray(undefined)).toBeNull();
  });
});

describe("hasFace", () => {
  it("is true only when a face is present", () => {
    expect(hasFace(resultWithFace())).toBe(true);
    expect(hasFace({ faceLandmarks: [] })).toBe(false);
    expect(hasFace(null)).toBe(false);
  });
});

describe("countValidFrames", () => {
  it("counts only frames containing a face", () => {
    expect(countValidFrames([[[0, 0, 0]], null, [[1, 1, 1]], null])).toBe(2);
    expect(countValidFrames([])).toBe(0);
    expect(countValidFrames([null, null])).toBe(0);
  });

  /**
   * The gate the capture loop applies before sending a window. Pinned here
   * because both sides of the boundary matter: 7 valid frames is sent, 6 is
   * withheld and no state is shown.
   */
  it("decides the send/withhold boundary at MIN_VALID_FRAMES", () => {
    const face = [[0, 0, 0]];
    const window = (valid) =>
      Array.from({ length: WINDOW_SIZE }, (_, i) => (i < valid ? face : null));

    expect(countValidFrames(window(MIN_VALID_FRAMES))).toBe(MIN_VALID_FRAMES);
    expect(countValidFrames(window(MIN_VALID_FRAMES)) >= MIN_VALID_FRAMES).toBe(true);
    expect(countValidFrames(window(MIN_VALID_FRAMES - 1)) >= MIN_VALID_FRAMES).toBe(
      false
    );
  });
});

describe("isLowLight", () => {
  it("warns below the threshold and not at or above it", () => {
    expect(isLowLight(LOW_LIGHT_THRESHOLD - 1)).toBe(true);
    expect(isLowLight(LOW_LIGHT_THRESHOLD)).toBe(false);
    expect(isLowLight(LOW_LIGHT_THRESHOLD + 1)).toBe(false);
  });

  /**
   * A null brightness means the video is not producing pixels yet. That is not
   * darkness, and warning about the room would be wrong and confusing.
   */
  it("does not warn when brightness could not be measured", () => {
    expect(isLowLight(null)).toBe(false);
  });
});

describe("constants that must agree with the backend", () => {
  /**
   * These are load-bearing. The model's input shape is (10, 9) and it was
   * trained at one frame per second. Changing either of these produces
   * confident wrong predictions rather than an error, which is why they are
   * pinned here as well as documented.
   */
  it("matches the model's window size and sampling rate", () => {
    expect(WINDOW_SIZE).toBe(10);
    expect(CAPTURE_INTERVAL_MS).toBe(1000);
  });

  it("requires a majority of the window to contain a face", () => {
    expect(MIN_VALID_FRAMES).toBeGreaterThan(WINDOW_SIZE / 2);
    expect(MIN_VALID_FRAMES).toBeLessThanOrEqual(WINDOW_SIZE);
  });
});

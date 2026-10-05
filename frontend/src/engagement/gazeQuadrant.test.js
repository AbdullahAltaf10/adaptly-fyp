// frontend/src/engagement/gazeQuadrant.test.js
import { describe, expect, it } from "vitest";
import { estimateGazeBand } from "./gazeQuadrant";

const LEFT_EYE = [33, 160, 158, 133, 153, 144];
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];
const LEFT_IRIS = [468, 469, 470, 471];
const RIGHT_IRIS = [473, 474, 475, 476];

/** Builds a 478-point landmark array with every point at (0.5, 0.5, 0), then
 * overrides the eye/iris groups so the mean iris y is `irisY` and the mean
 * eye y is 0.5 - reproducing the same averaging features.py itself does. */
function fixture(irisY) {
  const landmarks = Array.from({ length: 478 }, () => [0.5, 0.5, 0]);
  for (const index of [...LEFT_EYE, ...RIGHT_EYE]) landmarks[index] = [0.5, 0.5, 0];
  for (const index of [...LEFT_IRIS, ...RIGHT_IRIS]) landmarks[index] = [0.5, irisY, 0];
  return landmarks;
}

describe("estimateGazeBand", () => {
  it("returns null for a missing/too-short landmark array", () => {
    expect(estimateGazeBand(null)).toBeNull();
    expect(estimateGazeBand([[0, 0, 0]])).toBeNull();
  });

  it("reports 'top' when the iris sits above the measured population mean by more than one std dev", () => {
    // mean=-0.004969, std=0.001266 (scaler stats) -> top boundary is
    // 0.5 + (mean - std) since iris_y - eye_y should be very negative.
    const result = estimateGazeBand(fixture(0.5 - 0.01));
    expect(result.band).toBe("top");
  });

  it("reports 'bottom' when the iris sits below the mean by more than one std dev", () => {
    const result = estimateGazeBand(fixture(0.5 + 0.01));
    expect(result.band).toBe("bottom");
  });

  it("reports 'middle' at the population mean offset", () => {
    const result = estimateGazeBand(fixture(0.5 - 0.004969));
    expect(result.band).toBe("middle");
  });

  it("always reports the same fixed confidence, since its weight (not this value) encodes how coarse it is", () => {
    const result = estimateGazeBand(fixture(0.5));
    expect(result.confidence).toBe(1.0);
  });
});

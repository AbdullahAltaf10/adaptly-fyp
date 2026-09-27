/**
 * The sentence splitter behind focus isolation.
 *
 * The property that matters most is the last test in this file: nothing may be
 * lost. A learner must never find that turning on an accessibility setting
 * made a piece of their document disappear.
 */

import { describe, expect, it } from "vitest";

import { splitSentences } from "./sentences";

describe("splitSentences", () => {
  it("splits on full stops, question marks and exclamation marks", () => {
    expect(splitSentences("One. Two? Three!").map((s) => s.trim())).toEqual([
      "One.",
      "Two?",
      "Three!",
    ]);
  });

  it("keeps an abbreviation with its sentence", () => {
    const pieces = splitSentences("Use a model, e.g. an LSTM, for sequences. Then test it.");

    expect(pieces).toHaveLength(2);
    expect(pieces[0]).toContain("e.g. an LSTM");
  });

  it("does not split inside a decimal", () => {
    expect(splitSentences("Accuracy was 4.17 degrees.")).toHaveLength(1);
  });

  it("does not split on an initial", () => {
    const pieces = splitSentences("K. Wisiecka measured gaze accuracy. It was low.");

    expect(pieces).toHaveLength(2);
    expect(pieces[0]).toContain("K. Wisiecka");
  });

  it("keeps a closing quote or bracket with the sentence it ends", () => {
    const pieces = splitSentences('He said "stop." Then he left.');

    expect(pieces[0].trim()).toBe('He said "stop."');
  });

  it("treats repeated terminators as one ending", () => {
    expect(splitSentences("Really?! Yes.").map((s) => s.trim())).toEqual(["Really?!", "Yes."]);
  });

  it("returns one piece for text with no terminator", () => {
    expect(splitSentences("a heading with no full stop")).toEqual([
      "a heading with no full stop",
    ]);
  });

  it("returns nothing for empty input", () => {
    expect(splitSentences("")).toEqual([]);
    expect(splitSentences(null)).toEqual([]);
  });

  it("loses nothing: joining the pieces reproduces the input exactly", () => {
    const samples = [
      "One. Two? Three!",
      "Use a model, e.g. an LSTM. Accuracy was 4.17 degrees. Done.",
      'He said "stop." Then he left.',
      "  leading and trailing whitespace stays  ",
      "No terminator here",
      "Line one.\nLine two.\n\nLine three.",
      "K. Wisiecka et al. measured it. Version 2.1 was used.",
    ];

    for (const sample of samples) {
      expect(splitSentences(sample).join("")).toBe(sample);
    }
  });
});

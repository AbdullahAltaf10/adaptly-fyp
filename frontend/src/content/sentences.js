/**
 * Splitting a paragraph into sentences, for focus isolation.
 *
 * Scope objective 4.1 asks for "sentence-level focus isolation", so something
 * has to decide where a sentence ends. This is a heuristic, deliberately: a
 * real sentence tokenizer is a dependency and a download, and the cost of
 * being wrong here is low - a slightly long or short highlighted span, never
 * lost text, because every character of the input appears in exactly one
 * piece of the output.
 *
 * What it handles, because each of these appears in real study material:
 *
 *   - Common abbreviations (e.g., i.e., Dr., Fig., et al.) which end in a full
 *     stop without ending a sentence.
 *   - Decimals and version numbers - "GPT 4.5" is not two sentences.
 *   - Initials, as in "K. Wisiecka measured gaze accuracy".
 *   - Closing quotes and brackets after the terminator.
 *
 * What it does not handle: sentences that end without punctuation, and
 * abbreviations outside the list. Both degrade into a longer highlighted span
 * rather than into anything broken.
 */

const ABBREVIATIONS = new Set([
  "e.g", "i.e", "etc", "vs", "cf", "al", "fig", "eq", "no", "approx",
  "dr", "prof", "mr", "mrs", "ms", "st", "jr", "sr",
  "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
]);

const TERMINATORS = new Set([".", "!", "?"]);

/** Trailing characters that still belong to the sentence that just ended. */
const TRAILING = new Set(['"', "'", "”", "’", ")", "]", "}", "»"]);

function endsWithAbbreviation(text) {
  const match = text.match(/([A-Za-z.]+)\.$/);
  if (!match) return false;
  const word = match[1].toLowerCase().replace(/\.$/, "");
  if (ABBREVIATIONS.has(word)) return true;
  // A single letter before a full stop is an initial ("K. Wisiecka"), not the
  // end of a sentence.
  return word.length === 1;
}

/**
 * Split `text` into sentences.
 *
 * Every character of `text` is preserved across the returned pieces, including
 * the whitespace between sentences, which is kept on the end of the sentence
 * before it. Joining the result returns the input exactly. Text with no
 * terminator comes back as a single piece, and empty input as an empty array.
 */
export function splitSentences(text) {
  if (!text) return [];

  const pieces = [];
  let start = 0;
  let index = 0;

  while (index < text.length) {
    const character = text[index];

    if (TERMINATORS.has(character)) {
      let end = index + 1;

      // Swallow repeated terminators ("What?!") and any closing punctuation.
      while (end < text.length && (TERMINATORS.has(text[end]) || TRAILING.has(text[end]))) {
        end += 1;
      }

      const candidate = text.slice(start, end);
      const nextCharacter = text[end];

      // A terminator inside a number ("4.5") or an abbreviation does not end a
      // sentence. Neither does one with no whitespace after it, which is how
      // decimals and URLs read.
      const isDecimal =
        character === "." &&
        /[0-9]$/.test(text.slice(0, index)) &&
        /^[0-9]/.test(text.slice(end));
      const followedByBreak = nextCharacter === undefined || /\s/.test(nextCharacter);

      if (!isDecimal && followedByBreak && !endsWithAbbreviation(candidate.trimEnd())) {
        // Keep the whitespace that follows on this sentence, so joining the
        // pieces reproduces the paragraph exactly.
        let after = end;
        while (after < text.length && /\s/.test(text[after])) after += 1;
        pieces.push(text.slice(start, after));
        start = after;
        index = after;
        continue;
      }

      index = end;
      continue;
    }

    index += 1;
  }

  if (start < text.length) pieces.push(text.slice(start));
  return pieces;
}

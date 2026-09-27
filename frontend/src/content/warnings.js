/**
 * Module 2's content warnings, in words a learner can act on.
 *
 * `app/content/language.py` already detects these and stores them on every
 * document — the contract has carried a required `warnings` array since the
 * beginning. Nothing ever displayed them, so scope section 6.2's "a language
 * warning is shown if Urdu or low-confidence video transcription is detected"
 * was computed and then thrown away.
 *
 * Two rules for the wording below, both deliberate:
 *
 * **Say what it means for them, not what the system detected.** "non_english
 * content" is a classification; "detection may be less accurate" is the
 * consequence they can weigh.
 *
 * **Never frame it as the learner's problem.** These are limitations of our
 * pipeline — an English-trained engagement model, an imperfect transcriber —
 * not something they did wrong, and the copy says so.
 */

export const CONTENT_WARNING_LABELS = {
  urdu_content_reduced_accuracy:
    "This document is in Urdu. Reading support and engagement detection were " +
    "built and tested on English, so both will be less accurate here.",
  non_english_content:
    "This document is not in English. Reading support and engagement " +
    "detection were built and tested on English, so both will be less " +
    "accurate here.",
  mixed_script_content:
    "This document mixes more than one script. Some sections may be " +
    "simplified or summarised less well than others.",
  low_confidence_transcription:
    "This came from an automatic transcription that the transcriber was not " +
    "confident about. Some passages may not match what was said.",
  roman_urdu_not_detectable:
    "If this document is Urdu written in English letters, we cannot detect " +
    "that automatically — so it will be treated as English, and support will " +
    "be less accurate.",
};

/**
 * Warning codes we do not recognise are shown, not hidden.
 *
 * Module 2 can add a code without this file knowing about it. Dropping the
 * unknown ones would mean a warning that was deliberately raised silently
 * never reaches the learner, which is the failure this whole file exists to
 * fix. Showing the raw code is ugly; showing nothing is worse.
 */
export function describeContentWarning(code) {
  return CONTENT_WARNING_LABELS[code] ?? `This document was flagged: ${code}.`;
}

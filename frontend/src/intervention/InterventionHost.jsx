/**
 * What an intervention looks like on screen.
 *
 * Styling here is deliberately plain - this exists so the delivery path can be
 * seen working end to end, and the visual design comes later. Two constraints
 * are not cosmetic though, and should survive any redesign:
 *
 * **Nothing flashes, nothing interrupts.** Scope 6.4 asks for support
 * delivered inline "without any sound, flash, or alert". So: no modal, no
 * overlay, no focus stealing, no animation. `aria-live="polite"` rather than
 * `assertive`, so a screen reader mentions it at the next pause instead of
 * cutting in - an assertive live region is the alert the scope rules out.
 *
 * **No scores.** Scope 6.8 allows no engagement scores or state indicators
 * during an active session. The server already leaves confidence and the
 * evidence tier out of what it sends here, so there is nothing to leak, and
 * nothing below should start showing "we are 73% sure you are struggling".
 *
 * The original text is shown beside the rewrite rather than replacing it. A
 * learner cannot judge a rewrite they are not allowed to compare against, and
 * silently swapping the words under somebody mid-paragraph is exactly the kind
 * of interruption the scope is trying to avoid.
 */

import { useState } from "react";

import {
  ASSISTANT_HELP_PROMPT,
  BREAK_SUGGESTION,
  BULLET_SUMMARY,
  SIMPLIFY_CONTENT,
} from "./constants";

const panel = {
  border: "1px solid #c8d4e3",
  borderLeft: "4px solid #0b6bcb",
  borderRadius: "6px",
  background: "#f7faff",
  padding: "0.85rem 1rem",
  margin: "0.75rem 0",
  textAlign: "left",
  fontSize: "0.95rem",
};

const row = { display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" };
const quiet = { fontSize: "0.8rem", color: "#5a6b7d", margin: "0 0 0.5rem" };

/**
 * A generated rewrite or summary, with the original available beside it.
 *
 * No accept button. An automatic type is experienced the moment it is on
 * screen, which is why Module 8 measures it from `displayed` - so the buttons
 * here only end it.
 */
function GeneratedText({ intervention, content, onComplete, onDismiss }) {
  const [showOriginal, setShowOriginal] = useState(false);
  const isSummary = intervention.intervention_type === BULLET_SUMMARY;

  return (
    <section style={panel} aria-live="polite" data-testid="intervention-generated">
      <p style={quiet}>{intervention.reason}</p>
      <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
        {isSummary ? "The main points" : "A simpler version"}
      </h4>

      <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
        {content?.generated}
      </div>

      {showOriginal && (
        <div
          style={{
            whiteSpace: "pre-wrap",
            lineHeight: 1.6,
            marginTop: "0.75rem",
            paddingTop: "0.75rem",
            borderTop: "1px dashed #c8d4e3",
            color: "#44586c",
          }}
        >
          <strong style={{ display: "block", fontSize: "0.8rem" }}>Original</strong>
          {content?.original}
        </div>
      )}

      <div style={row}>
        <button onClick={onComplete}>Done</button>
        <button onClick={() => setShowOriginal((v) => !v)}>
          {showOriginal ? "Hide original" : "Show original"}
        </button>
        <button onClick={onDismiss}>Not helpful</button>
      </div>

      {/* Which generator wrote this. A fallback result must never be mistaken
          for model output, and this is a development instrument rather than
          something a learner needs, so it stays small and last. */}
      {content?.generator && content.generator !== "gemini" && (
        <p style={{ ...quiet, margin: "0.5rem 0 0" }}>
          Assembled from the passage itself, not rewritten.
        </p>
      )}
    </section>
  );
}

/**
 * A break suggestion or an assistant prompt.
 *
 * These two have an accept button because they have to. Module 8 does not
 * begin measuring a learner-initiated intervention until it is accepted, so
 * one that is only ever shown - however prominently - contributes nothing to
 * any recovery metric. A passive banner here would quietly make the whole
 * measurement chain useless.
 */
function LearnerChoice({ intervention, accepted, onAccept, onComplete, onDismiss }) {
  const isBreak = intervention.intervention_type === BREAK_SUGGESTION;

  if (accepted) {
    return (
      <section style={panel} aria-live="polite" data-testid="intervention-accepted">
        <p style={{ margin: 0 }}>
          {isBreak
            ? "Take as long as you need."
            : "The assistant is ready when you are."}
        </p>
        <div style={row}>
          <button onClick={onComplete}>
            {isBreak ? "I'm back" : "Done"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section style={panel} aria-live="polite" data-testid="intervention-choice">
      <p style={{ margin: 0 }}>{intervention.reason}</p>
      <div style={row}>
        <button onClick={onAccept}>
          {isBreak ? "Take a break" : "Ask the assistant"}
        </button>
        <button onClick={onDismiss}>Not now</button>
      </div>
    </section>
  );
}

/**
 * Picks the right one. Returns null when there is nothing to show, which is
 * most of the time - cooldown alone keeps this empty for two minutes after
 * anything fires.
 */
export default function InterventionHost({
  intervention,
  content,
  loading,
  accepted,
  onAccept,
  onComplete,
  onDismiss,
}) {
  if (loading) {
    return (
      <p style={quiet} aria-live="polite" data-testid="intervention-loading">
        Preparing something that might help...
      </p>
    );
  }

  if (!intervention) return null;

  const type = intervention.intervention_type;

  if (type === SIMPLIFY_CONTENT || type === BULLET_SUMMARY) {
    // Without content there is nothing to render. The hook reports `failed`
    // and clears in that case, so this is a guard rather than a state.
    if (!content?.generated) return null;
    return (
      <GeneratedText
        intervention={intervention}
        content={content}
        onComplete={onComplete}
        onDismiss={onDismiss}
      />
    );
  }

  if (type === BREAK_SUGGESTION || type === ASSISTANT_HELP_PROMPT) {
    return (
      <LearnerChoice
        intervention={intervention}
        accepted={accepted}
        onAccept={onAccept}
        onComplete={onComplete}
        onDismiss={onDismiss}
      />
    );
  }

  return null;
}

/**
 * What an intervention looks like on screen.
 *
 * Two constraints are not cosmetic and must survive any redesign:
 *
 * **Nothing flashes, nothing interrupts.** Scope 6.4 asks for support
 * delivered inline "without any sound, flash, or alert". So: no modal, no
 * overlay, no focus stealing, no animation on arrival. `aria-live="polite"`
 * rather than `assertive`, so a screen reader mentions it at the next pause
 * instead of cutting in - an assertive live region is the alert the scope
 * rules out. The card design below (a quiet left accent bar, no motion, no
 * colour louder than the rest of the page) is the visual expression of the
 * same rule, not a decoration on top of it.
 *
 * **No scores.** Scope 6.8 allows no engagement scores or state indicators
 * during an active session. The server already leaves confidence and the
 * evidence tier out of what it sends here, so there is nothing to leak, and
 * nothing below should start showing "we are 73% sure you are struggling".
 *
 * The original text is shown beside the rewrite rather than replacing it. A
 * learner cannot judge a rewrite they are not allowed to compare against, and
 * silently swapping the words under somebody mid-paragraph is exactly the
 * kind of interruption the scope is trying to avoid.
 */

import { Coffee, ListChecks, MessageCircleQuestion, Wand2 } from "lucide-react";
import { useState } from "react";

import {
  ASSISTANT_HELP_PROMPT,
  BREAK_SUGGESTION,
  BULLET_SUMMARY,
  SIMPLIFY_CONTENT,
} from "./constants";
import { Button } from "../ui";

const CARD =
  "rounded-card shadow-card border border-line border-l-4 border-l-accent " +
  "bg-surface p-4 my-3 text-left text-sm";

const ROW = "flex flex-wrap gap-2 mt-3";

/** The icon + label every card opens with, so the four types read consistently. */
function CardHeading({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="flex items-center justify-center w-7 h-7 rounded-full bg-info-soft text-accent shrink-0">
        <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
      </span>
      <h4 className="m-0 text-base font-semibold text-ink">{children}</h4>
    </div>
  );
}

/**
 * A generated rewrite or summary, with the original available beside it.
 *
 * No accept button. An automatic type is experienced the moment it is on
 * screen, which is why Module 8 measures it from `displayed` - so the buttons
 * here only end it.
 */
export function GeneratedText({ intervention, content, onComplete, onDismiss }) {
  const [showOriginal, setShowOriginal] = useState(false);
  const isSummary = intervention.intervention_type === BULLET_SUMMARY;

  return (
    <section className={CARD} aria-live="polite" data-testid="intervention-generated">
      <p className="m-0 mb-2 text-xs text-muted">{intervention.reason}</p>
      <CardHeading icon={isSummary ? ListChecks : Wand2}>
        {isSummary ? "The main points" : "A simpler version"}
      </CardHeading>

      <div className="whitespace-pre-wrap leading-relaxed text-ink">{content?.generated}</div>

      {showOriginal && (
        <div className="whitespace-pre-wrap leading-relaxed mt-3 pt-3 border-t border-dashed border-line text-muted">
          <strong className="block text-xs text-ink mb-1">Original</strong>
          {content?.original}
        </div>
      )}

      <div className={ROW}>
        <Button variant="secondary" onClick={onComplete}>
          Done
        </Button>
        <Button variant="quiet" onClick={() => setShowOriginal((v) => !v)}>
          {showOriginal ? "Hide original" : "Show original"}
        </Button>
        <Button variant="quiet" onClick={onDismiss}>
          Not helpful
        </Button>
      </div>

      {/* Which generator wrote this. A fallback result must never be mistaken
          for model output, and this is a development instrument rather than
          something a learner needs, so it stays small and last. */}
      {content?.generator && content.generator !== "gemini" && (
        <p className="text-xs text-muted mt-2 mb-0">
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
  const Icon = isBreak ? Coffee : MessageCircleQuestion;

  if (accepted) {
    return (
      <section className={CARD} aria-live="polite" data-testid="intervention-accepted">
        <CardHeading icon={Icon}>{isBreak ? "Taking a break" : "Assistant ready"}</CardHeading>
        <p className="m-0 text-ink">
          {isBreak ? "Take as long as you need." : "The assistant is ready when you are."}
        </p>
        <div className={ROW}>
          <Button variant="secondary" onClick={onComplete}>
            {isBreak ? "I'm back" : "Done"}
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className={CARD} aria-live="polite" data-testid="intervention-choice">
      <CardHeading icon={Icon}>{isBreak ? "Take a break?" : "Need a hand?"}</CardHeading>
      <p className="m-0 text-ink">{intervention.reason}</p>
      <div className={ROW}>
        <Button onClick={onAccept}>{isBreak ? "Take a break" : "Ask the assistant"}</Button>
        <Button variant="quiet" onClick={onDismiss}>
          Not now
        </Button>
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
      <p className="text-xs text-muted" aria-live="polite" data-testid="intervention-loading">
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

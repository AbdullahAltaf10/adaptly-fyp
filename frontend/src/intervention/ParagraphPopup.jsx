/**
 * The anchored, standalone popup for simplify_content/bullet_summary: a
 * popover card (see the 2026-09-30 design research below) that appears
 * beside whichever paragraph it is about, using Floating UI to pick
 * whichever side actually has room (useFloatingPlacement) instead of a
 * fixed "always on the right" rule. Own scroll for long content, a manual
 * dismiss and a collapse/reopen toggle.
 *
 * No inline Q&A here (an earlier version had one - removed 2026-09-30 on
 * explicit direction: this is not the place to have a conversation).
 * Further questions continue in the sticky AssistantPanel instead, seeded
 * with this popup's own content via onContinueInChat, so the same
 * persistent history the panel already reads (Task 3/9) is the one place a
 * conversation actually lives - this card is a notification of that
 * content, not a second chat surface.
 *
 * Pattern choice, and why (uxpatterns.dev's modal/popover/tooltip guidance,
 * plus general contextual-help UX research): the expanded card is a
 * *popover* - contextual, anchored, non-blocking, and it has real controls
 * in it (dismiss, collapse, continue-in-chat), which rules out a tooltip
 * (tooltips are for a brief, non-interactive glance) and a modal (blocks
 * the page, wrong for something auto-triggered while reading). The
 * *collapsed* state is a small badge with its own tooltip-style hover
 * preview - exactly the brief/non-interactive case a tooltip is for.
 *
 * Lifecycle (when it opens/closes) is owned by useParagraphPopup, not here -
 * this component only renders whatever it is currently told to. Full close
 * happens there too (intervention.current/content going null once the
 * learner has genuinely left the paragraph), which is what makes the badge
 * disappear along with the card - there's nothing badge-specific to hide.
 */
import { useState } from "react";
import { ArrowRight, Lightbulb, X } from "lucide-react";

import { GeneratedText } from "./InterventionHost";
import { useFloatingPlacement } from "./useFloatingPlacement";
import { Button } from "../ui";

// 2026-09-30 correction: the card must target the PARAGRAPH's own top-left
// or top-right corner - not the browser window's - as a compact card
// (~30-40% of the viewport width), not stretch to cover most of the page.
// This is already what useFloatingPlacement/computePosition does (its
// reference element is chunkElement, the paragraph itself, so x/y are
// computed relative to the paragraph's actual on-screen position and
// re-tracked on scroll via autoUpdate) - never a fixed window-corner
// position like a toast notification. Height must be a fixed, reasonable
// value with its own inline scroll - not tied to viewport height (vh),
// which made it grow or shrink unpredictably with window size instead of
// just being a fixed-size card. Width is expressed as a viewport-relative
// value (the ask was specifically about height, not width) but bounded so
// it never gets absurdly narrow or wide.
const POPUP_WIDTH_VW = "36vw";
const POPUP_MIN_WIDTH_PX = 280;
const POPUP_MAX_WIDTH_PX = 400;
const POPUP_HEIGHT_PX = 360;

function CollapsedBadge({ onToggleCollapsed, content }) {
  const [hovered, setHovered] = useState(false);
  const [badgeElement, setBadgeElement] = useState(null);
  const { floatingRef, x, y, ready } = useFloatingPlacement(badgeElement, {
    enabled: hovered,
    placement: "top",
  });

  return (
    <>
      <button
        ref={setBadgeElement}
        type="button"
        onClick={onToggleCollapsed}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        className="inline-flex items-center gap-1.5 rounded-full border border-line-strong
                   bg-surface px-3 py-1.5 text-xs font-medium text-ink shadow-card
                   hover:bg-page transition-colors duration-150"
      >
        <Lightbulb size={14} strokeWidth={1.75} aria-hidden="true" />
        Need help
      </button>
      {hovered && (
        <span
          ref={floatingRef}
          role="tooltip"
          style={{
            position: "fixed",
            top: ready ? y : -9999,
            left: ready ? x : -9999,
            width: 280,
          }}
          className="z-[900] rounded-md border border-line-strong bg-surface px-3 py-2
                     text-xs leading-relaxed text-ink shadow-floating"
        >
          {content.generated}
        </span>
      )}
    </>
  );
}

export default function ParagraphPopup({
  chunkElement,
  intervention,
  content,
  collapsed,
  onToggleCollapsed,
  onComplete,
  onDismiss,
  onContinueInChat,
}) {
  const { floatingRef, x, y, ready } = useFloatingPlacement(chunkElement, { placement: "right-start" });

  if (!content?.generated) return null;

  if (collapsed) {
    return <CollapsedBadge onToggleCollapsed={onToggleCollapsed} content={content} />;
  }

  // Should not happen - ContentViewer registers every chunk it renders, so
  // this always has an element for the intervention's own chunk_id - but
  // the content must still reach the learner if it ever does. Anchored
  // positioning is a presentation refinement, not a condition for showing
  // the content at all.
  const sizeStyle = { width: POPUP_WIDTH_VW, minWidth: POPUP_MIN_WIDTH_PX, maxWidth: POPUP_MAX_WIDTH_PX };
  const positionStyle = ready
    ? { position: "fixed", top: y, left: x, zIndex: 800, ...sizeStyle }
    : { position: "static", marginTop: 8, ...sizeStyle };

  return (
    <>
      <style>{`
        @keyframes adaptly-popup-in {
          from { opacity: 0; transform: translateY(4px) scale(0.98); }
          to { opacity: 1; transform: none; }
        }
      `}</style>
      <div
        ref={floatingRef}
        style={{
          ...positionStyle,
          height: POPUP_HEIGHT_PX,
          overflowY: "auto",
          animation: "adaptly-popup-in 180ms ease-out",
        }}
        className="rounded-card shadow-floating border border-line bg-surface"
      >
        <div className="flex justify-end gap-1 px-2 pt-2">
          <Button variant="quiet" onClick={onToggleCollapsed} aria-label="Collapse">
            Collapse
          </Button>
          <Button variant="quiet" onClick={onDismiss} aria-label="Dismiss">
            <X size={14} strokeWidth={1.75} aria-hidden="true" />
          </Button>
        </div>

        <GeneratedText
          intervention={intervention}
          content={content}
          onComplete={onComplete}
          onDismiss={onDismiss}
        />

        <div className="px-3 pb-3">
          <Button variant="secondary" className="w-full justify-center" onClick={onContinueInChat}>
            Continue in chat
            <ArrowRight size={14} strokeWidth={1.75} aria-hidden="true" />
          </Button>
        </div>
      </div>
    </>
  );
}

/**
 * What is on screen, and two things about it that are not styling.
 *
 * The visual design comes later. These pin the parts that must survive it:
 * a learner-initiated intervention has to have an accept action or it counts
 * for nothing, and nothing here may show an engagement score.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import InterventionHost from "./InterventionHost";
import {
  ASSISTANT_HELP_PROMPT,
  BREAK_SUGGESTION,
  BULLET_SUMMARY,
  SIMPLIFY_CONTENT,
} from "./constants";

function offered(type) {
  return {
    intervention_id: "i1",
    intervention_type: type,
    reason: "Signs of difficulty on this section after 20s.",
    reason_code: "struggling",
  };
}

const CONTENT = {
  generated: "A simpler version of the passage.",
  original: "The original, denser passage.",
  generator: "gemini",
  cached: false,
};

function show(props = {}) {
  const handlers = {
    onAccept: vi.fn(),
    onComplete: vi.fn(),
    onDismiss: vi.fn(),
  };
  render(<InterventionHost {...handlers} {...props} />);
  return handlers;
}

describe("nothing to show", () => {
  it("renders nothing on a normal window", () => {
    const { container } = render(<InterventionHost intervention={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a generated type whose text never arrived", () => {
    const { container } = render(
      <InterventionHost intervention={offered(SIMPLIFY_CONTENT)} content={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("generated text", () => {
  it("shows the rewrite", () => {
    show({ intervention: offered(SIMPLIFY_CONTENT), content: CONTENT });
    expect(screen.getByText(CONTENT.generated)).toBeInTheDocument();
  });

  /**
   * Scope 6.4 asks for support delivered inline rather than content being
   * replaced out from under somebody. A learner cannot judge a rewrite they
   * are not allowed to compare against.
   */
  it("can show the original beside it", async () => {
    show({ intervention: offered(SIMPLIFY_CONTENT), content: CONTENT });
    expect(screen.queryByText(CONTENT.original)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /show original/i }));
    expect(screen.getByText(CONTENT.original)).toBeInTheDocument();
  });

  it("says when the text was assembled rather than written by a model", () => {
    show({
      intervention: offered(BULLET_SUMMARY),
      content: { ...CONTENT, generator: "extractive" },
    });
    expect(screen.getByText(/not rewritten/i)).toBeInTheDocument();
  });

  it("does not claim model output was a fallback", () => {
    show({ intervention: offered(BULLET_SUMMARY), content: CONTENT });
    expect(screen.queryByText(/not rewritten/i)).not.toBeInTheDocument();
  });

  it("completing is one click", async () => {
    const handlers = show({
      intervention: offered(SIMPLIFY_CONTENT),
      content: CONTENT,
    });
    await userEvent.click(screen.getByRole("button", { name: /done/i }));
    expect(handlers.onComplete).toHaveBeenCalled();
  });
});

describe("the two that need the learner to act", () => {
  /**
   * The test this file exists for. Module 8 does not begin measuring a
   * learner-initiated intervention until it is accepted, so a passive banner
   * with no accept action would quietly make the whole measurement chain
   * useless while looking perfectly reasonable.
   */
  it.each([
    [BREAK_SUGGESTION, /take a break/i],
    [ASSISTANT_HELP_PROMPT, /ask the assistant/i],
  ])("%s offers an explicit accept action", async (type, label) => {
    const handlers = show({ intervention: offered(type) });
    await userEvent.click(screen.getByRole("button", { name: label }));
    expect(handlers.onAccept).toHaveBeenCalled();
  });

  it("can be declined", async () => {
    const handlers = show({ intervention: offered(BREAK_SUGGESTION) });
    await userEvent.click(screen.getByRole("button", { name: /not now/i }));
    expect(handlers.onDismiss).toHaveBeenCalled();
  });

  it("stays on screen once accepted, and can then be finished", async () => {
    const handlers = show({ intervention: offered(BREAK_SUGGESTION), accepted: true });
    expect(screen.getByTestId("intervention-accepted")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /i'm back/i }));
    expect(handlers.onComplete).toHaveBeenCalled();
  });
});

describe("what it must never show or do", () => {
  /**
   * Scope 6.8: no engagement scores or state indicators during an active
   * session. The server leaves confidence and the evidence tier out of what it
   * sends, so there is nothing to leak - this checks nothing reintroduces it.
   */
  it.each([SIMPLIFY_CONTENT, BREAK_SUGGESTION, ASSISTANT_HELP_PROMPT])(
    "shows no score for %s",
    (type) => {
      const { container } = render(
        <InterventionHost intervention={offered(type)} content={CONTENT} />
      );
      const text = container.textContent.toLowerCase();
      expect(text).not.toMatch(/\d+(\.\d+)?\s*%/);
      expect(text).not.toContain("confidence");
      expect(text).not.toContain("struggling");
      expect(text).not.toMatch(/\b(strong|broad)\b/);
    }
  );

  /**
   * Scope 6.4: "without any sound, flash, or alert". An assertive live region
   * interrupts a screen reader mid-sentence, which is the alert the scope
   * rules out; polite waits for a pause. A dialog would steal focus.
   */
  it("announces politely and never as a dialog", () => {
    const { container } = render(
      <InterventionHost intervention={offered(BREAK_SUGGESTION)} />
    );
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
    expect(container.querySelector('[aria-live="assertive"]')).toBeNull();
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

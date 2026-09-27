/**
 * The viewer's job is not "show the text" — that part is hard to get wrong.
 *
 * It is that every chunk reaches whoever is watching, because that is the
 * thing that fails silently. A viewer that renders perfectly and registers
 * nothing looks completely correct on screen while `simplify_content` and
 * `bullet_summary` quietly never fire, which is exactly the state Module 4
 * was in before this existed (issue #47).
 *
 * So these tests are mostly about `onChunkRef`.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ContentViewer from "./ContentViewer";

function chunk(id, order, text, extra = {}) {
  return { chunk_id: id, order, text, ...extra };
}

const CONTENT = {
  content_id: "c1",
  title: "Depreciation and amortisation",
  chunks: [
    chunk("ch-2", 2, "Amortisation spreads the cost of an intangible asset."),
    chunk("ch-1", 1, "Depreciation spreads the cost of a tangible asset.", {
      section_title: "Tangible assets",
    }),
    chunk("ch-3", 3, "Both match the expense to the periods that benefit."),
  ],
};

describe("registering chunks for dwell", () => {
  it("hands every chunk to onChunkRef with a real element", () => {
    const onChunkRef = vi.fn();
    render(<ContentViewer content={CONTENT} onChunkRef={onChunkRef} />);

    const registered = onChunkRef.mock.calls
      .filter(([, element]) => element !== null)
      .map(([id]) => id);

    expect(new Set(registered)).toEqual(new Set(["ch-1", "ch-2", "ch-3"]));
    for (const [, element] of onChunkRef.mock.calls) {
      if (element !== null) expect(element).toBeInstanceOf(HTMLElement);
    }
  });

  it("un-registers a chunk when the viewer goes away", () => {
    const onChunkRef = vi.fn();
    const { unmount } = render(
      <ContentViewer content={CONTENT} onChunkRef={onChunkRef} />
    );

    onChunkRef.mockClear();
    unmount();

    // `useDwell.register` reads a null element as "stop watching this chunk".
    // Without this the observer keeps dead nodes and dwell can be attributed
    // to a paragraph that is no longer on screen.
    const cleared = onChunkRef.mock.calls
      .filter(([, element]) => element === null)
      .map(([id]) => id);
    expect(new Set(cleared)).toEqual(new Set(["ch-1", "ch-2", "ch-3"]));
  });

  it("renders perfectly well with nobody watching", () => {
    // The seam is optional on purpose: Module 2 can show a document without
    // Module 4 being involved at all.
    expect(() => render(<ContentViewer content={CONTENT} />)).not.toThrow();
    expect(screen.getByText(/Amortisation spreads/)).toBeTruthy();
  });
});

describe("what the learner sees", () => {
  it("renders chunks in order, not in array order", () => {
    render(<ContentViewer content={CONTENT} />);
    const rendered = [...document.querySelectorAll("[data-chunk-id]")].map(
      (el) => el.getAttribute("data-chunk-id")
    );
    expect(rendered).toEqual(["ch-1", "ch-2", "ch-3"]);
  });

  it("shows a section title when there is one", () => {
    render(<ContentViewer content={CONTENT} />);
    expect(screen.getByText("Tangible assets")).toBeTruthy();
  });

  it("never marks a critical section on screen", () => {
    // Module 4 halves its dwell threshold for `is_critical`, but telling a
    // learner which paragraph is being watched harder is pressure, and scope
    // 6.4 asks for support delivered without disruption.
    const critical = {
      ...CONTENT,
      // Deliberately no form of the word "critical" in the text itself, so a
      // match can only come from the viewer marking it.
      chunks: [chunk("ch-1", 1, "Report a near miss within 24 hours.", { is_critical: true })],
    };
    const { container } = render(<ContentViewer content={critical} />);
    expect(container.textContent).not.toMatch(/critical|important|required/i);
  });

  it("shows no engagement state, score or dwell anywhere", () => {
    // Scope 6.8: nothing measured may be visible during an active session.
    const { container } = render(<ContentViewer content={CONTENT} />);
    expect(container.textContent).not.toMatch(
      /focused|drifting|struggling|fatigued|dwell|confidence|%/i
    );
  });
});

describe("documents that are not there", () => {
  it("says so rather than rendering an empty page", () => {
    render(<ContentViewer content={null} />);
    expect(screen.getByText(/No document loaded/)).toBeTruthy();
  });

  it("handles a document with no chunks", () => {
    render(<ContentViewer content={{ title: "Empty", chunks: [] }} />);
    expect(screen.getByText(/no readable sections/i)).toBeTruthy();
  });

  it("handles chunks being absent entirely", () => {
    expect(() =>
      render(<ContentViewer content={{ title: "No chunks key" }} />)
    ).not.toThrow();
  });
});

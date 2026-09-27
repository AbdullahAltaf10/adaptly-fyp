/**
 * Focus isolation in the reading screen — scope objective 4.1's
 * "sentence-level focus isolation".
 *
 * The setting existed and was saved to the profile. `useAccessibility` wrote
 * `data-focus-isolation="on"` to <html>. Nothing read it, so switching it on
 * changed nothing at all on screen.
 *
 * These tests pin the two things that make it safe: it only happens when the
 * learner asked for it, and it never removes text.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import ContentViewer from "./ContentViewer";

const content = {
  title: "Engagement detection",
  chunks: [
    {
      chunk_id: "c1",
      order: 1,
      text: "The camera reads numbers. It never records video. Nothing is stored.",
    },
  ],
};

function enableIsolation() {
  document.documentElement.setAttribute("data-focus-isolation", "on");
}

afterEach(() => {
  document.documentElement.removeAttribute("data-focus-isolation");
});

describe("ContentViewer focus isolation", () => {
  it("does nothing at all when the learner has not asked for it", () => {
    const { container } = render(<ContentViewer content={content} />);

    expect(container.querySelectorAll(".focus-sentence")).toHaveLength(0);
    expect(screen.getByText(/The camera reads numbers/)).toBeInTheDocument();
  });

  it("splits the paragraph into sentences when it is on", () => {
    enableIsolation();

    const { container } = render(<ContentViewer content={content} />);

    expect(container.querySelectorAll(".focus-sentence")).toHaveLength(3);
  });

  it("dims nothing until the learner points at a sentence", () => {
    enableIsolation();

    const { container } = render(<ContentViewer content={content} />);

    expect(container.querySelectorAll(".focus-sentence-dimmed")).toHaveLength(0);
  });

  it("dims the other sentences once one is pointed at", async () => {
    enableIsolation();

    const { container } = render(<ContentViewer content={content} />);
    const sentences = container.querySelectorAll(".focus-sentence");
    await userEvent.hover(sentences[1]);

    expect(sentences[1].className).not.toContain("focus-sentence-dimmed");
    expect(sentences[0].className).toContain("focus-sentence-dimmed");
    expect(sentences[2].className).toContain("focus-sentence-dimmed");
  });

  it("stops dimming when the pointer leaves the paragraph", async () => {
    enableIsolation();

    const { container } = render(<ContentViewer content={content} />);
    const sentences = container.querySelectorAll(".focus-sentence");
    await userEvent.hover(sentences[0]);
    await userEvent.unhover(container.querySelector(".focus-isolation-paragraph"));

    expect(container.querySelectorAll(".focus-sentence-dimmed")).toHaveLength(0);
  });

  it("never removes text: the whole paragraph is still there", () => {
    enableIsolation();

    const { container } = render(<ContentViewer content={content} />);

    const paragraph = container.querySelector("[data-chunk-id='c1'] p");
    expect(paragraph.textContent).toBe(content.chunks[0].text);
  });

  it("leaves a one-sentence paragraph alone", () => {
    enableIsolation();

    const { container } = render(
      <ContentViewer
        content={{ title: "t", chunks: [{ chunk_id: "c1", order: 1, text: "Only one." }] }}
      />
    );

    expect(container.querySelectorAll(".focus-sentence")).toHaveLength(0);
    expect(screen.getByText("Only one.")).toBeInTheDocument();
  });

  it("still registers chunk elements for dwell tracking", () => {
    enableIsolation();
    const registered = [];

    render(
      <ContentViewer
        content={content}
        onChunkRef={(chunkId, element) => registered.push([chunkId, element])}
      />
    );

    expect(registered.some(([chunkId, element]) => chunkId === "c1" && element)).toBe(true);
  });
});

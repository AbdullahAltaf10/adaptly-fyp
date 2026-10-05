import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Floating UI's real autoUpdate() relies on ResizeObserver/RAF plumbing
// jsdom does not provide, which hangs a test run rather than failing it.
// Its own positioning logic is a trusted external library, already
// exercised (with this project's OWN wiring around it) in
// useFloatingPlacement.test.js - this file only needs a resolved position
// so ParagraphPopup's own rendering/behavior can be asserted on.
vi.mock("@floating-ui/dom", () => ({
  computePosition: () => Promise.resolve({ x: 660, y: 92, placement: "right-start" }),
  autoUpdate: () => () => {},
  offset: () => ({}),
  flip: () => ({}),
  shift: () => ({}),
}));

import ParagraphPopup from "./ParagraphPopup";

function elementAt(rect) {
  const el = document.createElement("div");
  Object.defineProperty(el, "getBoundingClientRect", { value: () => rect });
  return el;
}

const intervention = { intervention_id: "i1", chunk_id: "3", reason: "Signs of difficulty." };
const content = { generated: "A simpler version of the paragraph.", original: "The original passage." };

function baseProps(overrides = {}) {
  return {
    chunkElement: elementAt({ top: 100, left: 0, width: 600, height: 80 }),
    intervention,
    content,
    collapsed: false,
    onToggleCollapsed: vi.fn(),
    onComplete: vi.fn(),
    onDismiss: vi.fn(),
    onContinueInChat: vi.fn(),
    ...overrides,
  };
}

describe("ParagraphPopup", () => {
  it("falls back to an unpositioned (bottom-of-flow) render when there is no chunk element to anchor to, rather than rendering nothing", () => {
    render(<ParagraphPopup {...baseProps({ chunkElement: null })} />);
    expect(screen.getByText(content.generated)).toBeInTheDocument();
  });

  it("renders nothing when there is no generated content yet", () => {
    const { container } = render(<ParagraphPopup {...baseProps({ content: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the generated text, anchored to the paragraph", async () => {
    const { container } = render(<ParagraphPopup {...baseProps()} />);
    expect(screen.getByText(content.generated)).toBeInTheDocument();
    await waitFor(() =>
      expect(container.querySelector(".shadow-floating")).toHaveStyle({ position: "fixed" })
    );
  });

  it("has no inline question input - further questions continue in the sticky panel instead", () => {
    render(<ParagraphPopup {...baseProps()} />);
    expect(screen.queryByPlaceholderText(/ask about this section/i)).not.toBeInTheDocument();
  });

  it("uses a fixed pixel height, never a viewport-height (vh) unit", async () => {
    const { container } = render(<ParagraphPopup {...baseProps()} />);
    await waitFor(() => expect(container.querySelector(".shadow-floating")).toHaveStyle({ position: "fixed" }));
    const card = container.querySelector(".shadow-floating");
    expect(card.style.height).toMatch(/^\d+px$/);
    expect(card.style.height).not.toMatch(/vh/);
    expect(card.style.maxHeight).toBe("");
  });

  it("stays a compact card - bounded width, not a full-page-width panel", async () => {
    const { container } = render(<ParagraphPopup {...baseProps()} />);
    await waitFor(() => expect(container.querySelector(".shadow-floating")).toHaveStyle({ position: "fixed" }));
    const card = container.querySelector(".shadow-floating");
    expect(card.style.maxWidth).toMatch(/^\d+px$/);
    expect(Number.parseInt(card.style.maxWidth, 10)).toBeLessThanOrEqual(400);
  });

  it("calls onContinueInChat from its redirect button", () => {
    const onContinueInChat = vi.fn();
    render(<ParagraphPopup {...baseProps({ onContinueInChat })} />);
    fireEvent.click(screen.getByRole("button", { name: /continue in chat/i }));
    expect(onContinueInChat).toHaveBeenCalledTimes(1);
  });

  it("collapses to a small 'Need help' badge, hiding the generated content", () => {
    render(<ParagraphPopup {...baseProps({ collapsed: true })} />);
    expect(screen.queryByText(content.generated)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /need help/i })).toBeInTheDocument();
  });

  it("calls onToggleCollapsed when the badge is clicked (reopens the full card)", () => {
    const onToggleCollapsed = vi.fn();
    render(<ParagraphPopup {...baseProps({ collapsed: true, onToggleCollapsed })} />);
    fireEvent.click(screen.getByRole("button", { name: /need help/i }));
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it("shows a tooltip preview of the content on hover, without fully reopening", () => {
    render(<ParagraphPopup {...baseProps({ collapsed: true })} />);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByRole("button", { name: /need help/i }));
    expect(screen.getByRole("tooltip")).toHaveTextContent(content.generated);
  });

  it("hides the hover preview again once the pointer leaves the badge", () => {
    render(<ParagraphPopup {...baseProps({ collapsed: true })} />);
    const badge = screen.getByRole("button", { name: /need help/i });
    fireEvent.mouseEnter(badge);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.mouseLeave(badge);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("calls onDismiss from its own close control", () => {
    const onDismiss = vi.fn();
    render(<ParagraphPopup {...baseProps({ onDismiss })} />);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("calls onToggleCollapsed from the expanded card's own collapse control", () => {
    const onToggleCollapsed = vi.fn();
    render(<ParagraphPopup {...baseProps({ onToggleCollapsed })} />);
    fireEvent.click(screen.getByRole("button", { name: /collapse/i }));
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });
});

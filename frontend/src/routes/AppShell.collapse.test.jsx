/**
 * The sidebar's manual collapse toggle.
 *
 * Independent of the existing md: breakpoint behavior, which already goes
 * icon-only below md regardless - this lets a learner reclaim width on a
 * desktop-size screen too, and remembers the choice for next time (a
 * per-viewer convenience, so it is allowed to just fall back to expanded if
 * storage is unavailable rather than needing to work reliably).
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { email: "a@b.co", emailVerified: true, providerData: [] },
    profile: { uid: "u", mode: "learner" },
    loading: false,
  }),
}));
vi.mock("firebase/auth", () => ({ signOut: vi.fn(), getAuth: () => ({}), GoogleAuthProvider: class {} }));
vi.mock("../auth/firebase", () => ({ auth: {}, googleProvider: {} }));

import AppShell from "./AppShell";

const STORAGE_KEY = "adaptly.sidebarCollapsed";

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/library"]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/library" element={<p>documents</p>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  window.localStorage.clear();
});

describe("AppShell sidebar collapse", () => {
  it("starts expanded by default, with labels visible from md upward", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Main" });
    const labelSpans = [...nav.querySelectorAll("a span.truncate")];
    expect(labelSpans.length).toBeGreaterThan(0);
    // "sr-only md:not-sr-only" - visible from md upward, not force-hidden.
    for (const span of labelSpans) expect(span.className).toContain("md:not-sr-only");
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
  });

  it("collapses on click, force-hiding labels at every width and flipping the toggle's accessible name", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const span of nav.querySelectorAll("a span.truncate")) {
      // Plain "sr-only" (no "md:not-sr-only" escape hatch) - hidden regardless
      // of viewport width, unlike the default responsive behavior.
      expect(span.className).not.toContain("md:not-sr-only");
    }
  });

  it("expands again on a second click", () => {
    renderShell();
    const toggle = () => screen.getByRole("button", { name: /(collapse|expand) sidebar/i });
    fireEvent.click(toggle());
    fireEvent.click(toggle());
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
  });

  it("remembers a collapsed preference across a remount", () => {
    const { unmount } = renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    unmount();

    renderShell();
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });

  it("falls back to expanded when localStorage throws (private mode, blocked storage)", () => {
    const original = window.localStorage.getItem;
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => renderShell()).not.toThrow();
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
    window.localStorage.getItem = original;
  });
});

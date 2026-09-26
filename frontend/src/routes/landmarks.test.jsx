/**
 * A page must have exactly one <main> landmark.
 *
 * Screen readers use it to jump straight to the content, and two of them make
 * that shortcut ambiguous. This was already true of the old placeholder shell
 * (its <main> wrapped the dashboard's <main>), which is exactly why it is worth
 * pinning now that the shell is being replaced: it is easy to reintroduce when
 * a page and its frame each think they own the landmark.
 *
 * Tested against the real route tree with the data layer stubbed, so it fails
 * on a nested main wherever one comes from, not just in the file that wrote it.
 */

import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { email: "a@b.co", emailVerified: true, providerData: [] },
    profile: { uid: "u", display_name: "Sara" },
    loading: false,
  }),
}));
vi.mock("firebase/auth", () => ({ signOut: vi.fn(), getAuth: () => ({}), GoogleAuthProvider: class {} }));
vi.mock("../auth/firebase", () => ({ auth: {}, googleProvider: {} }));
vi.mock("../analytics/api", () => ({
  fetchMostRecentCompletedSession: () => Promise.resolve(null),
  fetchSessionAnalytics: () => Promise.resolve({}),
}));

import AppShell from "./AppShell";
import AnalyticsDashboardContainer from "../pages/AnalyticsDashboardContainer";

function mainCount(path, element) {
  const { container } = render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path={path} element={element} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
  return container.querySelectorAll("main, [role='main']").length;
}

describe("landmarks", () => {
  it("has exactly one main on an ordinary page", () => {
    expect(mainCount("/settings", <p>plain page</p>)).toBe(1);
  });

  it("has exactly one main on the analytics page, which brings its own", () => {
    expect(mainCount("/analytics", <AnalyticsDashboardContainer />)).toBe(1);
  });
});

/**
 * Who sees which nav item.
 *
 * Scope 6.10 makes the compliance attestation report a corporate feature, and
 * the HR list is for `hr_admin` only. The backend enforces both (owner-only on
 * a session's report, `require_hr_admin` on the list), so this is not a
 * security boundary - it is about not advertising a corporate concept to an
 * individual learner studying their own PDF.
 *
 * The profile shape is swapped per test, which is why this file mocks
 * `useAuth` through a mutable holder rather than a fixed return value.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authState = { value: null };

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => authState.value,
}));
vi.mock("firebase/auth", () => ({ signOut: vi.fn(), getAuth: () => ({}), GoogleAuthProvider: class {} }));
vi.mock("../auth/firebase", () => ({ auth: {}, googleProvider: {} }));

import AppShell from "./AppShell";

function renderNavFor(profile) {
  authState.value = {
    currentUser: { email: "a@b.co", emailVerified: true, providerData: [] },
    profile,
    loading: false,
  };
  render(
    <MemoryRouter initialEntries={["/library"]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/library" element={<p>documents</p>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
  return screen.getByRole("navigation", { name: "Main" });
}

describe("AppShell nav", () => {
  beforeEach(() => {
    authState.value = null;
  });

  it("gives every signed-in user the learner items", () => {
    const nav = renderNavFor({ uid: "u", mode: "learner" });

    expect(nav).toHaveTextContent("My documents");
    expect(nav).toHaveTextContent("Study session");
    expect(nav).toHaveTextContent("Analytics");
  });

  it("does not offer an individual learner the compliance report", () => {
    const nav = renderNavFor({ uid: "u", mode: "learner" });

    expect(nav).not.toHaveTextContent("Compliance report");
    expect(nav).not.toHaveTextContent("HR compliance");
  });

  it("offers a corporate employee their own compliance report, but not the HR list", () => {
    const nav = renderNavFor({ uid: "u", mode: "corporate", corporate_role: "employee" });

    expect(nav).toHaveTextContent("Compliance report");
    expect(nav).not.toHaveTextContent("HR compliance");
  });

  it("offers an HR admin both", () => {
    const nav = renderNavFor({ uid: "u", mode: "corporate", corporate_role: "hr_admin" });

    expect(nav).toHaveTextContent("Compliance report");
    expect(nav).toHaveTextContent("HR compliance");
  });

  it("offers neither when the profile has not loaded yet", () => {
    const nav = renderNavFor(null);

    expect(nav).not.toHaveTextContent("Compliance report");
    expect(nav).not.toHaveTextContent("HR compliance");
  });
});

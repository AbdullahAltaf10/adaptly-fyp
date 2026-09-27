/**
 * The gate has five outcomes and only one of them is "let them through".
 *
 * Both classic auth-flow bugs live here, and neither throws: bouncing a
 * signed-in learner to the sign-in page because their profile had not loaded
 * yet, and looping /verify-email -> /verify-email forever. So each state gets
 * its own test rather than being covered by one happy path.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authState = { value: {} };
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => authState.value,
}));

import RequireAuth from "./RequireAuth";

function renderAt(path = "/study", { requireVerified = true } = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/study"
          element={
            <RequireAuth requireVerified={requireVerified}>
              <p>the protected page</p>
            </RequireAuth>
          }
        />
        <Route path="/signin" element={<p>sign in screen</p>} />
        <Route path="/register" element={<p>register screen</p>} />
        <Route path="/verify-email" element={<p>verify screen</p>} />
      </Routes>
    </MemoryRouter>
  );
}

const verifiedUser = { emailVerified: true, providerData: [{ providerId: "password" }] };
const unverifiedUser = { emailVerified: false, providerData: [{ providerId: "password" }] };
const googleUser = { emailVerified: true, providerData: [{ providerId: "google.com" }] };

beforeEach(() => {
  authState.value = {};
});

describe("states that must not redirect", () => {
  it("waits while the session is still loading", () => {
    // The bug this prevents: redirecting to /signin on the first frame,
    // before Firebase has restored the session, so every refresh signs you out.
    authState.value = { loading: true, currentUser: null, profile: null };
    renderAt();
    expect(screen.queryByText("sign in screen")).toBeNull();
    expect(screen.getByText(/checking your session/i)).toBeTruthy();
  });

  it("waits while the profile is still being fetched", () => {
    authState.value = { loading: false, currentUser: verifiedUser, profile: null, profileError: null };
    renderAt();
    expect(screen.queryByText("register screen")).toBeNull();
    expect(screen.getByText(/loading your profile/i)).toBeTruthy();
  });
});

describe("where each state sends the learner", () => {
  it("signed out -> sign in", () => {
    authState.value = { loading: false, currentUser: null, profile: null };
    renderAt();
    expect(screen.getByText("sign in screen")).toBeTruthy();
  });

  it("signed in with no profile row -> register", () => {
    // Normal for a first Google sign-in: Firebase has them, the backend does not.
    authState.value = {
      loading: false,
      currentUser: verifiedUser,
      profile: null,
      profileError: { kind: "no_profile" },
    };
    renderAt();
    expect(screen.getByText("register screen")).toBeTruthy();
  });

  it("unverified address -> verify email", () => {
    authState.value = { loading: false, currentUser: unverifiedUser, profile: { uid: "u" } };
    renderAt();
    expect(screen.getByText("verify screen")).toBeTruthy();
  });

  it("fully ready -> the page", () => {
    authState.value = { loading: false, currentUser: verifiedUser, profile: { uid: "u" } };
    renderAt();
    expect(screen.getByText("the protected page")).toBeTruthy();
  });
});

describe("the two loops this guard has to avoid", () => {
  it("does not send a Google user to verify an address Google already verified", () => {
    // Firebase marks them verified, so that screen would have nothing for them
    // to click - a dead end rather than a step.
    authState.value = {
      loading: false,
      currentUser: { ...googleUser, emailVerified: false },
      profile: { uid: "u" },
    };
    renderAt();
    expect(screen.getByText("the protected page")).toBeTruthy();
  });

  it("lets the verify screen itself render without a verified address", () => {
    // requireVerified={false} is how /verify-email avoids redirecting to itself.
    authState.value = { loading: false, currentUser: unverifiedUser, profile: { uid: "u" } };
    renderAt("/study", { requireVerified: false });
    expect(screen.getByText("the protected page")).toBeTruthy();
  });
});

describe("when the backend is down", () => {
  it("says so instead of pretending it is a sign-in problem", () => {
    // Sending them to /signin here would be a lie, and they would sign in
    // successfully and land right back on the same failure.
    authState.value = {
      loading: false,
      currentUser: verifiedUser,
      profile: null,
      profileError: { kind: "unreachable" },
    };
    renderAt();
    expect(screen.queryByText("sign in screen")).toBeNull();
    expect(screen.getByText(/backend is not responding/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
  });
});

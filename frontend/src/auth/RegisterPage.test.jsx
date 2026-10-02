/**
 * Registration actually reaching the backend with a request it will accept.
 *
 * Two real bugs lived here, both invisible until someone actually tried to
 * register: the learner option sent `mode=individual`, which the backend has
 * never accepted (`app/auth/roles.py`'s `VALID_MODES` is `{"learner",
 * "corporate"}`), and the corporate option sent no `role` at all, which the
 * backend requires whenever mode is "corporate". Every registration - email
 * or Google, learner or corporate - failed with 400.
 *
 * These tests pin the literal query string sent, so a value drifting out of
 * sync with the backend again fails here instead of only in a browser.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const firebaseAuth = {
  createUserWithEmailAndPassword: vi.fn(),
  sendEmailVerification: vi.fn(),
  updateProfile: vi.fn(),
};

vi.mock("firebase/auth", () => ({
  createUserWithEmailAndPassword: (...args) => firebaseAuth.createUserWithEmailAndPassword(...args),
  sendEmailVerification: (...args) => firebaseAuth.sendEmailVerification(...args),
  updateProfile: (...args) => firebaseAuth.updateProfile(...args),
}));

vi.mock("./firebase", () => ({ auth: {}, googleProvider: {} }));

const auth = { currentUser: null, refreshProfile: vi.fn() };
vi.mock("./AuthContext", () => ({ useAuth: () => auth }));

const apiClient = { post: vi.fn() };
vi.mock("../api/client", () => ({
  default: { post: (...args) => apiClient.post(...args) },
  classifyError: () => "bad_request",
}));

import RegisterPage from "./RegisterPage";

const draw = () =>
  render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>
  );

function lastRegisterQuery() {
  const [url] = apiClient.post.mock.calls.at(-1);
  return new URL(url, "http://x").searchParams;
}

beforeEach(() => {
  firebaseAuth.createUserWithEmailAndPassword.mockReset();
  firebaseAuth.sendEmailVerification.mockReset();
  firebaseAuth.updateProfile.mockReset();
  apiClient.post.mockReset().mockResolvedValue({});
  auth.currentUser = null;
  auth.refreshProfile.mockReset().mockResolvedValue(undefined);
  firebaseAuth.createUserWithEmailAndPassword.mockResolvedValue({ user: { uid: "u1" } });
});

async function fillEmailSignup(user) {
  await user.type(screen.getByLabelText(/your name/i), "Sara Ahmed");
  await user.type(screen.getByLabelText(/email address/i), "sara@example.com");
  // "Password" the label reads as "Password (required)" (a screen-reader-only
  // suffix), and "^password" - unanchored at the end - still cannot match
  // "Confirm password", which starts with a different word.
  await user.type(screen.getByLabelText(/^password/i), "a-strong-password");
  await user.type(screen.getByLabelText(/confirm password/i), "a-strong-password");
}

describe("RegisterPage: what actually reaches the backend", () => {
  it("sends mode=learner for the default (Individual learner) option, not mode=individual", async () => {
    const user = userEvent.setup();
    draw();

    await fillEmailSignup(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    const query = lastRegisterQuery();
    expect(query.get("mode")).toBe("learner");
    expect(query.get("mode")).not.toBe("individual");
  });

  it("sends role=employee alongside mode=corporate", async () => {
    const user = userEvent.setup();
    draw();

    await fillEmailSignup(user);
    await user.selectOptions(screen.getByLabelText(/how will you use adaptly/i), "corporate");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    const query = lastRegisterQuery();
    expect(query.get("mode")).toBe("corporate");
    expect(query.get("role")).toBe("employee");
  });

  it("never sends a role for a learner registration", async () => {
    const user = userEvent.setup();
    draw();

    await fillEmailSignup(user);
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    expect(lastRegisterQuery().get("role")).toBeNull();
  });

  it("finishes setup with the same correct mode for a Google user completing step 2", async () => {
    auth.currentUser = { uid: "g1", displayName: "Sara", email: "sara@gmail.com" };
    const user = userEvent.setup();
    draw();

    await user.click(screen.getByRole("button", { name: /finish setting up/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    expect(lastRegisterQuery().get("mode")).toBe("learner");
    // Step 1 (the credential) already happened via Google - must not run again.
    expect(firebaseAuth.createUserWithEmailAndPassword).not.toHaveBeenCalled();
  });
});

describe("RegisterPage: live validation, not only on submit", () => {
  it("shows nothing for an untouched field", () => {
    draw();

    expect(screen.queryByText(/enter a password/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/does not look like an email/i)).not.toBeInTheDocument();
  });

  it("shows a password problem as soon as the learner leaves the field, before submitting", async () => {
    const user = userEvent.setup();
    draw();

    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.tab();

    expect(await screen.findByText(/use at least 8 characters/i)).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("clears the password message as soon as it becomes long enough, without leaving the field", async () => {
    const user = userEvent.setup();
    draw();

    const passwordField = screen.getByLabelText(/^password/i);
    await user.type(passwordField, "short");
    await user.tab();
    await screen.findByText(/use at least 8 characters/i);

    await user.type(passwordField, "-enough-now");

    await waitFor(() =>
      expect(screen.queryByText(/use at least 8 characters/i)).not.toBeInTheDocument()
    );
  });

  it("flags a mismatched confirmation the moment it is left, and updates it as the password changes", async () => {
    const user = userEvent.setup();
    draw();

    await user.type(screen.getByLabelText(/^password/i), "correct-horse-battery");
    await user.type(screen.getByLabelText(/confirm password/i), "does-not-match");
    await user.tab();

    expect(await screen.findByText(/do not match/i)).toBeInTheDocument();

    // Fixing the ORIGINAL password field must also clear a confirmation
    // error that was about the old value - it is not only re-checked when
    // the confirmation field itself is touched again.
    await user.clear(screen.getByLabelText(/^password/i));
    await user.type(screen.getByLabelText(/^password/i), "does-not-match");

    await waitFor(() => expect(screen.queryByText(/do not match/i)).not.toBeInTheDocument());
  });

  it("shows an invalid email as soon as the field is left", async () => {
    const user = userEvent.setup();
    draw();

    await user.type(screen.getByLabelText(/email address/i), "not-an-email");
    await user.tab();

    expect(await screen.findByText(/does not look like an email/i)).toBeInTheDocument();
  });
});

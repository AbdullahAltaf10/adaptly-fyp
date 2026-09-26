/**
 * The auth screens, tested for the behaviour that is easy to get wrong rather
 * than for "does it render".
 *
 * Two of these are security properties, not UX ones: the reset screen must
 * look identical whether or not the address is registered, and the sign-in
 * screen must not turn Firebase's deliberately vague error into a specific
 * one.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const firebaseAuth = {
  signInWithEmailAndPassword: vi.fn(),
  signInWithPopup: vi.fn(),
  sendPasswordResetEmail: vi.fn(),
};

vi.mock("firebase/auth", () => ({
  signInWithEmailAndPassword: (...args) => firebaseAuth.signInWithEmailAndPassword(...args),
  signInWithPopup: (...args) => firebaseAuth.signInWithPopup(...args),
  sendPasswordResetEmail: (...args) => firebaseAuth.sendPasswordResetEmail(...args),
  GoogleAuthProvider: class {},
  getAuth: () => ({}),
}));

vi.mock("./firebase", () => ({ auth: {}, googleProvider: {} }));

import ForgotPasswordPage from "./ForgotPasswordPage";
import SignInPage from "./SignInPage";

const draw = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

beforeEach(() => {
  for (const fn of Object.values(firebaseAuth)) fn.mockReset();
});

describe("signing in", () => {
  it("does not call Firebase when the email is obviously malformed", async () => {
    const user = userEvent.setup();
    draw(<SignInPage />);

    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "whatever");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(firebaseAuth.signInWithEmailAndPassword).not.toHaveBeenCalled();
    expect(await screen.findByText(/does not look like an email/i)).toBeTruthy();
  });

  it("does NOT validate the password's format on sign-in", async () => {
    // Rules may have changed since the account was made. Refusing to even try
    // strands someone whose existing password is short but correct.
    const user = userEvent.setup();
    firebaseAuth.signInWithEmailAndPassword.mockResolvedValue({});
    draw(<SignInPage />);

    await user.type(screen.getByLabelText(/email/i), "sara@example.com");
    await user.type(screen.getByLabelText(/password/i), "short");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(firebaseAuth.signInWithEmailAndPassword).toHaveBeenCalled());
  });

  it("shows a sentence, never a Firebase error code", async () => {
    const user = userEvent.setup();
    firebaseAuth.signInWithEmailAndPassword.mockRejectedValue({ code: "auth/invalid-credential" });
    draw(<SignInPage />);

    await user.type(screen.getByLabelText(/email/i), "sara@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toMatch(/auth\//);
    // And must not reveal whether the address is registered.
    expect(alert.textContent).not.toMatch(/no account|not found/i);
  });

  it("treats a closed Google popup as a non-event, not an error", async () => {
    const user = userEvent.setup();
    firebaseAuth.signInWithPopup.mockRejectedValue({ code: "auth/popup-closed-by-user" });
    draw(<SignInPage />);

    await user.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => expect(firebaseAuth.signInWithPopup).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does explain a blocked popup, which the learner can fix", async () => {
    const user = userEvent.setup();
    firebaseAuth.signInWithPopup.mockRejectedValue({ code: "auth/popup-blocked" });
    draw(<SignInPage />);

    await user.click(screen.getByRole("button", { name: /continue with google/i }));
    expect(await screen.findByText(/blocked the sign-in window/i)).toBeTruthy();
  });
});

describe("resetting a password", () => {
  it("confirms without saying whether the account exists", async () => {
    const user = userEvent.setup();
    firebaseAuth.sendPasswordResetEmail.mockResolvedValue();
    draw(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), "sara@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    const confirmation = await screen.findByText(/if there is an Adaptly account/i);
    expect(confirmation).toBeTruthy();
  });

  it("looks identical for an address with no account", async () => {
    // Otherwise the form becomes a way to ask whether any given address is
    // registered - the same enumeration the sign-in page avoids.
    const user = userEvent.setup();
    firebaseAuth.sendPasswordResetEmail.mockRejectedValue({ code: "auth/user-not-found" });
    draw(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), "nobody@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/if there is an Adaptly account/i)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does surface a real failure, which is not an enumeration risk", async () => {
    const user = userEvent.setup();
    firebaseAuth.sendPasswordResetEmail.mockRejectedValue({ code: "auth/network-request-failed" });
    draw(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), "sara@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

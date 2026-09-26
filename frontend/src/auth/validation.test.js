import { describe, expect, it } from "vitest";

import {
  MIN_PASSWORD_LENGTH,
  REGISTRATION_MODES,
  collectErrors,
  describeAuthError,
  validateEmail,
  validateMode,
  validateName,
  validatePassword,
  validatePasswordConfirmation,
} from "./validation";

describe("email", () => {
  it("accepts addresses a strict regex would wrongly reject", () => {
    // Plus-addressing, long TLDs and subdomains are all real. A validator that
    // rejects these annoys more people than it protects, and the actual check
    // is whether the verification mail arrives.
    for (const address of [
      "sara+adaptly@example.com",
      "a@b.co",
      "first.last@mail.university.edu.pk",
      "user@sub.domain.technology",
    ]) {
      expect(validateEmail(address), address).toBeNull();
    }
  });

  it("catches the shapes that are definitely wrong", () => {
    for (const bad of ["", "   ", "no-at-sign", "@example.com", "user@", "user@host"]) {
      expect(validateEmail(bad), bad).toBeTruthy();
    }
  });

  it("does not fail on surrounding whitespace, which is usually a paste artefact", () => {
    expect(validateEmail("  sara@example.com  ")).toBeNull();
  });
});

describe("password", () => {
  it("only asks for length", () => {
    expect(validatePassword("correct horse battery")).toBeNull();
    expect(validatePassword("a".repeat(MIN_PASSWORD_LENGTH))).toBeNull();
  });

  it("rejects anything shorter than Firebase will accept", () => {
    expect(validatePassword("a".repeat(MIN_PASSWORD_LENGTH - 1))).toBeTruthy();
    expect(validatePassword("")).toBeTruthy();
  });

  it("does not demand symbols or digits", () => {
    // Composition rules push people to "Password1!" and to reusing it.
    expect(validatePassword("alllowercaseletters")).toBeNull();
  });

  it("checks the confirmation matches", () => {
    expect(validatePasswordConfirmation("abcdefgh", "abcdefgh")).toBeNull();
    expect(validatePasswordConfirmation("abcdefgh", "abcdefgi")).toBeTruthy();
    expect(validatePasswordConfirmation("abcdefgh", "")).toBeTruthy();
  });
});

describe("name and mode", () => {
  it("accepts ordinary names and rejects empty ones", () => {
    expect(validateName("Sara Ahmed")).toBeNull();
    expect(validateName("  ")).toBeTruthy();
    expect(validateName("x")).toBeTruthy();
  });

  it("only offers modes the backend will actually grant", () => {
    // hr_admin is granted from an allow-list server-side and 403s otherwise,
    // so offering it here would advertise something the server refuses.
    const values = REGISTRATION_MODES.map((m) => m.value);
    expect(values).toContain("individual");
    expect(values).toContain("corporate");
    expect(values).not.toContain("hr_admin");
  });

  it("rejects a mode that is not on the list", () => {
    expect(validateMode("hr_admin")).toBeTruthy();
    expect(validateMode("")).toBeTruthy();
    expect(validateMode("individual")).toBeNull();
  });
});

describe("collectErrors", () => {
  it("keeps only the checks that failed, so a form can show them all at once", () => {
    expect(collectErrors({ a: null, b: "broken", c: null })).toEqual({ b: "broken" });
  });

  it("returns an empty object when everything passes", () => {
    expect(collectErrors({ a: null })).toEqual({});
  });
});

describe("Firebase error codes", () => {
  it("never shows a learner a raw error code", () => {
    for (const code of [
      "auth/invalid-credential",
      "auth/email-already-in-use",
      "auth/too-many-requests",
      "auth/popup-blocked",
    ]) {
      const message = describeAuthError({ code });
      expect(message).not.toMatch(/auth\//);
      expect(message.length).toBeGreaterThan(10);
    }
  });

  it("stays vague about whether an account exists", () => {
    // Firebase collapses wrong-password and no-such-user into one code on
    // purpose, so an attacker cannot enumerate addresses. The copy has to
    // preserve that.
    const message = describeAuthError({ code: "auth/invalid-credential" });
    expect(message).not.toMatch(/no account|not registered|does not exist/i);
  });

  it("falls back to something readable for an unmapped code", () => {
    expect(describeAuthError({ code: "auth/something-new" })).toBeTruthy();
    expect(describeAuthError(null)).toBeTruthy();
  });
});

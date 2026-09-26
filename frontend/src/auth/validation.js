/**
 * Client-side validation for the auth forms.
 *
 * **This is a convenience, never a guarantee.** Everything here can be
 * bypassed by anyone with a terminal, so nothing security-relevant may depend
 * on it. The backend re-checks what matters — `resolve_registration_role`
 * refuses to grant a privileged role on request no matter what this file
 * says, and Firebase enforces its own password rules server-side.
 *
 * What it *is* for: telling a learner what is wrong before they wait for a
 * round trip and get a Firebase error code instead of a sentence.
 *
 * Every validator returns a message string, or null when the value is fine.
 * That shape is what lets `Field` wire the message to the input for screen
 * readers without each form inventing its own convention.
 */

// Deliberately permissive. Email syntax is famously not a regex, and a strict
// pattern rejects real addresses (plus-addressing, new TLDs, unicode local
// parts) far more often than it catches typos. The real check is whether the
// verification email arrives, which is why verification exists at all.
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Firebase rejects anything shorter, with an error code rather than a sentence. */
export const MIN_PASSWORD_LENGTH = 8;

export function validateEmail(value) {
  const email = (value ?? "").trim();
  if (!email) return "Enter your email address.";
  if (!EMAIL_SHAPE.test(email)) return "That does not look like an email address.";
  return null;
}

export function validatePassword(value) {
  const password = value ?? "";
  if (!password) return "Enter a password.";
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  // No composition rules on purpose. Forcing a symbol and a digit pushes people
  // towards "Password1!" and towards reusing it; length is the property that
  // actually helps, and Firebase checks its own rules on top.
  return null;
}

/** Only used where the learner is choosing a password, not signing in. */
export function validatePasswordConfirmation(password, confirmation) {
  if (!confirmation) return "Re-enter the password.";
  if (password !== confirmation) return "The two passwords do not match.";
  return null;
}

export function validateName(value) {
  const name = (value ?? "").trim();
  if (!name) return "Enter your name.";
  if (name.length < 2) return "That name looks too short.";
  if (name.length > 100) return "That name is too long.";
  return null;
}

/**
 * Must match the backend's accepted values (`users/contracts.py`).
 *
 * `hr_admin` is not offered here at all. The backend grants it only to an
 * address on its own allow-list and returns 403 otherwise, so putting it in a
 * dropdown would be offering something the server will refuse — a worse
 * experience than not showing it.
 */
export const REGISTRATION_MODES = [
  { value: "individual", label: "Individual learner", hint: "Studying on your own" },
  { value: "corporate", label: "Corporate employee", hint: "Assigned training from an employer" },
];

export function validateMode(value) {
  if (!value) return "Choose how you will be using Adaptly.";
  if (!REGISTRATION_MODES.some((m) => m.value === value)) return "Choose one of the options.";
  return null;
}

/**
 * Run a set of validators and return `{ field: message }` for the ones that failed.
 *
 * Forms use this so that submitting shows *every* problem at once. Revealing
 * them one per submit is the pattern that makes people give up.
 */
export function collectErrors(checks) {
  const errors = {};
  for (const [field, message] of Object.entries(checks)) {
    if (message) errors[field] = message;
  }
  return errors;
}

/**
 * Firebase's error codes, in words.
 *
 * The raw codes leak into the UI otherwise — a learner should not be shown
 * `auth/invalid-credential`. Anything unmapped falls through to a generic
 * sentence rather than the code.
 */
const FIREBASE_MESSAGES = {
  "auth/invalid-email": "That does not look like an email address.",
  "auth/user-disabled": "This account has been disabled. Contact your administrator.",
  "auth/user-not-found": "No account found with that email address.",
  "auth/wrong-password": "That password is not correct.",
  // Modern Firebase returns this instead of user-not-found/wrong-password, on
  // purpose, so an attacker cannot use the error to discover which addresses
  // are registered. The wording has to stay vague for the same reason.
  "auth/invalid-credential": "That email address and password do not match an account.",
  "auth/email-already-in-use": "An account already exists with that email address.",
  "auth/weak-password": `Use at least ${MIN_PASSWORD_LENGTH} characters.`,
  "auth/too-many-requests": "Too many attempts. Wait a few minutes and try again.",
  "auth/network-request-failed": "Could not reach the server. Check your connection.",
  "auth/popup-closed-by-user": "The sign-in window was closed before finishing.",
  "auth/popup-blocked": "Your browser blocked the sign-in window. Allow pop-ups and try again.",
  "auth/cancelled-popup-request": "Another sign-in window is already open.",
  "auth/operation-not-allowed": "This sign-in method is not enabled for this project.",
  "auth/requires-recent-login": "Sign in again before making this change.",
};

export function describeAuthError(error) {
  const code = error?.code;
  if (code && FIREBASE_MESSAGES[code]) return FIREBASE_MESSAGES[code];
  if (code === "auth/internal-error") return "Something went wrong signing you in. Try again.";
  return error?.message || "Something went wrong. Try again.";
}

/**
 * Request a password reset link.
 *
 * **This screen reports success even when the address is not registered, and
 * that is deliberate.** Saying "no account found" turns the form into a way to
 * ask whether any given address has an Adaptly account, which is exactly what
 * Firebase's own `auth/invalid-credential` on the sign-in page exists to
 * prevent. So the confirmation is phrased as "if there is an account, a link
 * is on its way" — true in both cases, useful in one, and revealing in
 * neither.
 *
 * `auth/user-not-found` is therefore swallowed on purpose. Everything else
 * (network failure, rate limiting, a malformed address) is still shown,
 * because those are problems the learner can act on.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { sendPasswordResetEmail } from "firebase/auth";

import { auth } from "./firebase";
import { collectErrors, describeAuthError, validateEmail } from "./validation";
import { Alert, Button, Card, CenteredPage, Field, Input } from "../ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);

    const found = collectErrors({ email: validateEmail(email) });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setBusy(true);
    try {
      await sendPasswordResetEmail(auth, email.trim());
      setSent(true);
    } catch (err) {
      // See the note above: this one must look identical to success.
      if (err?.code === "auth/user-not-found") {
        setSent(true);
      } else {
        setError(describeAuthError(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <CenteredPage>
      <Card
        title="Reset your password"
        subtitle="We will email you a link to choose a new one."
      >
        {error && <Alert tone="error">{error}</Alert>}

        {sent ? (
          <>
            <Alert tone="success" title="Check your inbox">
              If there is an Adaptly account for <strong>{email.trim()}</strong>, a reset link is
              on its way. It can take a minute, and it may land in spam.
            </Alert>
            <Button variant="secondary" onClick={() => setSent(false)}>
              Use a different address
            </Button>
          </>
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <Field label="Email address" error={errors.email} required>
              {(aria) => (
                <Input
                  {...aria}
                  type="email"
                  name="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  invalid={Boolean(errors.email)}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
            </Field>

            <Button type="submit" className="w-full" busy={busy} busyLabel="Sending...">
              Send reset link
            </Button>
          </form>
        )}

        <p className="mt-4 text-sm text-muted">
          <Link to="/signin" className="text-accent hover:underline">
            Back to sign in
          </Link>
        </p>
      </Card>
    </CenteredPage>
  );
}

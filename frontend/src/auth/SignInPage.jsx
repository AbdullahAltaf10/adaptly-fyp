/**
 * Sign in, with Google or an email and password.
 *
 * Both routes end at the same Firebase session, so the rest of the app never
 * has to care which was used. What differs is the failure modes, and those are
 * where the care goes:
 *
 * - **Google's popup can be blocked or closed.** Both are ordinary, neither is
 *   an error the learner caused, and both need different advice.
 * - **Firebase deliberately will not say whether an address is registered.**
 *   `auth/invalid-credential` covers both wrong-password and no-such-user so
 *   an attacker cannot enumerate accounts. The copy has to stay vague for the
 *   same reason, which is why "email or password is incorrect" is right and
 *   "no account found" would not be.
 */

import { Fingerprint, Lock, LogIn, Mail } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { signInWithCustomToken, signInWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { startAuthentication, WebAuthnError } from "@simplewebauthn/browser";

import { auth, googleProvider } from "./firebase";
import { passkeyLoginOptions, passkeyLoginVerify } from "./security";
import { describeAuthError, validateEmail } from "./validation";
import { Alert, Button, Card, CenteredPage, Field, Input } from "../ui";

function passkeyPromptWasCancelled(err) {
  if (err?.name === "NotAllowedError") return true;
  return err instanceof WebAuthnError && err.cause?.name === "NotAllowedError";
}

export default function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [passkeyBusy, setPasskeyBusy] = useState(false);

  // Where they were headed before being bounced here, so signing in returns
  // them to it rather than dumping everyone on the same landing page.
  const destination = location.state?.from ?? "/";

  // Only the email is shape-checked, live once the field is left - not only
  // on submit, so a mistyped address is caught before waiting on Firebase.
  // Validating the password's format on a *sign-in* form is wrong: the rules
  // may have changed since the account was made, and refusing to even attempt
  // it strands the learner with no route forward except a reset they may not
  // need.
  const emailError = validateEmail(email);
  const errors = { email: emailTouched ? emailError : null };

  const handleEmailSignIn = async (event) => {
    event.preventDefault();
    setFormError(null);
    setEmailTouched(true);
    if (emailError) return;

    setBusy(true);
    try {
      await signInWithEmailAndPassword(auth, email.trim(), password);
      navigate(destination, { replace: true });
    } catch (error) {
      setFormError(describeAuthError(error));
    } finally {
      setBusy(false);
    }
  };

  const handlePasskey = async () => {
    setFormError(null);
    setEmailTouched(true);
    if (emailError) return;

    setPasskeyBusy(true);
    try {
      const { options, challenge_id: challengeId } = await passkeyLoginOptions(email.trim());
      const credential = await startAuthentication({ optionsJSON: options });
      const { custom_token: customToken } = await passkeyLoginVerify(challengeId, credential);
      await signInWithCustomToken(auth, customToken);
      navigate(destination, { replace: true });
    } catch (error) {
      if (passkeyPromptWasCancelled(error)) {
        // Same treatment as a closed Google popup: not an error to alarm
        // anyone with, they just changed their mind.
      } else if (error?.response?.status === 404) {
        setFormError(
          error.response.data?.detail ||
            "No passkey is set up for this email yet. Sign in with your password instead."
        );
      } else {
        setFormError("Could not sign in with a passkey. Try again, or use your password.");
      }
    } finally {
      setPasskeyBusy(false);
    }
  };

  const handleGoogle = async () => {
    setFormError(null);
    setGoogleBusy(true);
    try {
      await signInWithPopup(auth, googleProvider);
      navigate(destination, { replace: true });
    } catch (error) {
      // Closing the window yourself is not a failure worth shouting about.
      if (error?.code === "auth/popup-closed-by-user") {
        setGoogleBusy(false);
        return;
      }
      setFormError(describeAuthError(error));
    } finally {
      setGoogleBusy(false);
    }
  };

  return (
    <CenteredPage>
      <Card title="Sign in to Adaptly" subtitle="Continue with Google, or use your email address.">
        {formError && <Alert tone="error">{formError}</Alert>}

        <Button
          variant="secondary"
          className="w-full mb-4"
          onClick={handleGoogle}
          busy={googleBusy}
          busyLabel="Opening Google..."
        >
          Continue with Google
        </Button>

        <div className="flex items-center gap-3 mb-4 text-muted text-sm" aria-hidden="true">
          <span className="h-px flex-1 bg-line" />
          or
          <span className="h-px flex-1 bg-line" />
        </div>

        <form onSubmit={handleEmailSignIn} noValidate>
          <Field
            label={
              <span className="inline-flex items-center gap-1.5">
                <Mail size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                Email address
              </span>
            }
            error={errors.email}
            required
          >
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
                onBlur={() => setEmailTouched(true)}
              />
            )}
          </Field>

          <Field
            label={
              <span className="inline-flex items-center gap-1.5">
                <Lock size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                Password
              </span>
            }
            required
          >
            {(aria) => (
              <Input
                {...aria}
                type="password"
                name="password"
                autoComplete="current-password"
                placeholder="Your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>

          <Button type="submit" className="w-full" busy={busy} busyLabel="Signing in...">
            <LogIn size={16} strokeWidth={1.75} aria-hidden="true" />
            Sign in
          </Button>

          <Button
            type="button"
            variant="secondary"
            className="w-full mt-2"
            onClick={handlePasskey}
            busy={passkeyBusy}
            busyLabel="Follow the prompt..."
          >
            <Fingerprint size={16} strokeWidth={1.75} aria-hidden="true" />
            Sign in with a passkey
          </Button>
        </form>

        <div className="mt-4 flex flex-col gap-2 text-sm">
          <Link to="/forgot-password" className="text-accent hover:underline">
            Forgotten your password?
          </Link>
          <span className="text-muted">
            New here?{" "}
            <Link to="/register" className="text-accent hover:underline">
              Create an account
            </Link>
          </span>
        </div>
      </Card>
    </CenteredPage>
  );
}

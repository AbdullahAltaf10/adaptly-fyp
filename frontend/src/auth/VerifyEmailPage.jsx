/**
 * "Check your inbox" — the screen that asks for permission to use the address.
 *
 * Three things here are deliberate:
 *
 * **Firebase will not tell you the address was verified until the token is
 * refreshed.** `currentUser.emailVerified` is read from a cached ID token, so
 * clicking the link in the email changes nothing on this tab until we call
 * `reload()`. Without that, a learner who verified correctly sits here being
 * told to check their inbox again, which looks like the email is broken.
 *
 * **Resending is rate-limited on our side too.** Firebase returns
 * `auth/too-many-requests` eventually, but a learner who clicks four times in
 * five seconds deserves a countdown rather than a lockout they did not know
 * they were approaching.
 *
 * **Google accounts arrive already verified.** Google has confirmed the
 * address, so this screen must never block them - it redirects instead of
 * asking them to verify something already verified.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { sendEmailVerification, signOut } from "firebase/auth";

import { auth } from "./firebase";
import { useAuth } from "./AuthContext";
import { describeAuthError } from "./validation";
import { Alert, Button, Card, CenteredPage } from "../ui";

const RESEND_COOLDOWN_SECONDS = 60;

/** How often to re-check, for the common case of verifying in another tab. */
const POLL_INTERVAL_MS = 4000;

export default function VerifyEmailPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();

  const [checking, setChecking] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);

  const check = useCallback(
    async ({ announce = false } = {}) => {
      if (!auth.currentUser) return false;
      if (announce) setChecking(true);
      try {
        // The whole point: refresh the token before reading the flag.
        await auth.currentUser.reload();
        if (auth.currentUser.emailVerified) {
          navigate("/", { replace: true });
          return true;
        }
        if (announce) setError("That address is still unverified. Check your inbox and spam folder.");
        return false;
      } catch (err) {
        if (announce) setError(describeAuthError(err));
        return false;
      } finally {
        if (announce) setChecking(false);
      }
    },
    [navigate]
  );

  // Most people verify by opening the link in a different tab, then come back
  // to this one expecting it to have noticed.
  useEffect(() => {
    const timer = setInterval(() => check(), POLL_INTERVAL_MS);
    const onFocus = () => check();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [check]);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const resend = async () => {
    setError(null);
    setSending(true);
    try {
      await sendEmailVerification(auth.currentUser);
      setSent(true);
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (err) {
      setError(describeAuthError(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <CenteredPage>
      <Card
        title="Confirm your email address"
        subtitle={`We sent a link to ${currentUser?.email ?? "your address"}. Open it to finish setting up.`}
      >
        {error && <Alert tone="error">{error}</Alert>}
        {sent && !error && (
          <Alert tone="success">
            Sent. It can take a minute to arrive — check your spam folder if it does not.
          </Alert>
        )}

        <p className="text-muted mb-4">
          We check for this automatically, so you can open the link in another tab and come
          straight back here.
        </p>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => check({ announce: true })} busy={checking} busyLabel="Checking...">
            I have confirmed it
          </Button>

          <Button
            variant="secondary"
            onClick={resend}
            busy={sending}
            busyLabel="Sending..."
            disabled={cooldown > 0}
          >
            {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend the email"}
          </Button>
        </div>

        <p className="mt-6 text-sm text-muted">
          Wrong address?{" "}
          <button
            type="button"
            className="text-accent hover:underline"
            onClick={() => signOut(auth).then(() => navigate("/signin", { replace: true }))}
          >
            Sign out and start again
          </button>
        </p>
      </Card>
    </CenteredPage>
  );
}

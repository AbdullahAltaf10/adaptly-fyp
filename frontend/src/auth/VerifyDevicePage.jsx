/**
 * "Check your inbox" for a new device — the device-trust 2FA gate.
 *
 * Deliberately different from email verification: this is not about proving
 * the address, it is about recognising the BROWSER. Once the code is entered
 * correctly, this device is trusted for this account from then on — signing
 * in again tomorrow from the same browser skips this screen entirely. That
 * is the whole point (see the design note in AuthContext.jsx): a learner
 * should never be asked for a code they already proved they can receive.
 */

import { useState } from "react";
import { KeyRound, Mail, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { getDeviceId } from "./deviceId";
import { sendDeviceCode, verifyDeviceCode } from "./security";
import { classifyError } from "../api/client";
import { Alert, Button, Card, CenteredPage, Field, Input } from "../ui";

const RESEND_COOLDOWN_SECONDS = 30;

function describeSendError(err) {
  if (err?.response?.status === 429) {
    return err.response.data?.detail || "A code was just sent. Wait a moment before trying again.";
  }
  if (err?.response?.status === 503) {
    return "Device verification email is not set up yet. Contact an administrator.";
  }
  if (classifyError(err) === "unreachable") {
    return "Could not reach the server. Check your connection and try again.";
  }
  return "Could not send a verification code. Try again.";
}

export default function VerifyDevicePage() {
  const { currentUser, refreshDeviceTrust } = useAuth();
  const navigate = useNavigate();
  const deviceId = getDeviceId();

  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);

  const startCooldown = () => {
    setCooldown(RESEND_COOLDOWN_SECONDS);
    const tick = () =>
      setCooldown((n) => {
        if (n <= 1) return 0;
        setTimeout(tick, 1000);
        return n - 1;
      });
    setTimeout(tick, 1000);
  };

  const send = async () => {
    setError(null);
    setSending(true);
    try {
      await sendDeviceCode(deviceId);
      setSent(true);
      startCooldown();
    } catch (err) {
      setError(describeSendError(err));
    } finally {
      setSending(false);
    }
  };

  const verify = async (event) => {
    event.preventDefault();
    setError(null);
    setVerifying(true);
    try {
      await verifyDeviceCode(deviceId, code.trim());
      await refreshDeviceTrust();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err?.response?.data?.detail || "That code did not work. Check it and try again.");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <CenteredPage>
      <Card
        title={
          <span className="inline-flex items-center gap-2">
            <ShieldCheck size={20} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
            Verify this device
          </span>
        }
        subtitle={`For your security, we don't recognise this browser yet. We'll email a code to ${currentUser?.email ?? "your address"}.`}
      >
        {error && <Alert tone="error">{error}</Alert>}

        {!sent ? (
          <Button onClick={send} busy={sending} busyLabel="Sending...">
            <Mail size={16} strokeWidth={1.75} aria-hidden="true" />
            Email me a code
          </Button>
        ) : (
          <>
            <Alert tone="success">
              Sent. Enter the 6-digit code below — it expires in 10 minutes.
            </Alert>

            <form onSubmit={verify} noValidate>
              <Field
                label={
                  <span className="inline-flex items-center gap-1.5">
                    <KeyRound size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
                    Verification code
                  </span>
                }
                required
              >
                {(aria) => (
                  <Input
                    {...aria}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    placeholder="123456"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  />
                )}
              </Field>

              <div className="flex flex-wrap gap-2">
                <Button type="submit" busy={verifying} busyLabel="Verifying..." disabled={code.length !== 6}>
                  Verify and continue
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={send}
                  busy={sending}
                  busyLabel="Sending..."
                  disabled={cooldown > 0}
                >
                  {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                </Button>
              </div>
            </form>
          </>
        )}

        <p className="mt-6 text-sm text-muted">
          Once verified, this browser will not be challenged again on this account.
        </p>
      </Card>
    </CenteredPage>
  );
}

/**
 * "Sign-in and devices" — passkeys and the browsers trusted for 2FA.
 *
 * Two independent lists, both scoped to the signed-in account:
 *
 * - **Passkeys** replace a password entirely (Face ID / Windows Hello /
 *   fingerprint via WebAuthn). Adding one here is the registration ceremony;
 *   using one to sign in happens from SignInPage instead, with nobody
 *   signed in yet - see app/auth/passkeys.py for why those are split.
 * - **Trusted devices** are the browsers that already passed the emailed-code
 *   challenge (VerifyDevicePage) and so are not asked again. Revoking one
 *   here is how a learner forces a re-challenge - lost laptop, shared
 *   computer, anything that makes "we already trust this browser" wrong.
 *
 * A cancelled passkey prompt (closing the OS dialog, letting it time out) is
 * treated the same way a closed Google popup is on SignInPage: a non-event,
 * not an error to alarm someone with.
 */

import { useEffect, useState } from "react";
import { startRegistration, browserSupportsWebAuthn, WebAuthnError } from "@simplewebauthn/browser";
import { KeyRound, Laptop, Plus, ShieldCheck, Trash2 } from "lucide-react";

import {
  guessDeviceLabel,
  listPasskeys,
  listTrustedDevices,
  passkeyRegisterOptions,
  passkeyRegisterVerify,
  revokePasskey,
  revokeTrustedDevice,
} from "./security";
import { Alert, Button, Card } from "../ui";

function userCancelled(err) {
  // The browser's own dismissal/timeout surfaces as a NotAllowedError,
  // either directly or wrapped as WebAuthnError's `cause`. Every other
  // WebAuthnError (e.g. re-registering an already-known authenticator) is a
  // real problem worth telling the learner about, not a silent no-op.
  if (err?.name === "NotAllowedError") return true;
  return err instanceof WebAuthnError && err.cause?.name === "NotAllowedError";
}

function EmptyRow({ children }) {
  return <p className="text-muted text-sm">{children}</p>;
}

function ListRow({ icon: Icon, label, detail, onRemove, removing }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2 border-b border-line last:border-b-0">
      <span className="inline-flex items-center gap-2 min-w-0">
        <Icon size={16} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
        <span className="min-w-0">
          <span className="block truncate">{label}</span>
          {detail && <span className="block text-sm text-muted">{detail}</span>}
        </span>
      </span>
      <Button variant="quiet" onClick={onRemove} busy={removing} busyLabel="Removing...">
        <Trash2 size={14} strokeWidth={1.75} aria-hidden="true" />
        Remove
      </Button>
    </li>
  );
}

export default function SecuritySettings() {
  const [passkeys, setPasskeys] = useState(null);
  const [devices, setDevices] = useState(null);
  const [error, setError] = useState(null);
  const [addingPasskey, setAddingPasskey] = useState(false);
  const [removingId, setRemovingId] = useState(null);

  const load = async () => {
    try {
      const [pk, dv] = await Promise.all([listPasskeys(), listTrustedDevices()]);
      setPasskeys(pk);
      setDevices(dv);
    } catch {
      setPasskeys([]);
      setDevices([]);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const addPasskey = async () => {
    setError(null);
    setAddingPasskey(true);
    try {
      const { options, challenge_id: challengeId } = await passkeyRegisterOptions();
      const credential = await startRegistration({ optionsJSON: options });
      await passkeyRegisterVerify(challengeId, credential, guessDeviceLabel());
      await load();
    } catch (err) {
      if (!userCancelled(err)) {
        setError(err?.response?.data?.detail || "Could not add that passkey. Try again.");
      }
    } finally {
      setAddingPasskey(false);
    }
  };

  const removePasskey = async (credentialId) => {
    setRemovingId(credentialId);
    try {
      await revokePasskey(credentialId);
      await load();
    } finally {
      setRemovingId(null);
    }
  };

  const removeDevice = async (deviceId) => {
    setRemovingId(deviceId);
    try {
      await revokeTrustedDevice(deviceId);
      await load();
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <Card
      title={
        <span className="inline-flex items-center gap-2">
          <ShieldCheck size={20} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
          Sign-in and devices
        </span>
      }
      subtitle="Passkeys let you sign in without a password. Trusted devices skip the emailed code."
      className="mt-6"
    >
      {error && <Alert tone="error">{error}</Alert>}

      <section className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-medium m-0">Passkeys</h3>
          {browserSupportsWebAuthn() && (
            <Button variant="secondary" onClick={addPasskey} busy={addingPasskey} busyLabel="Follow the prompt...">
              <Plus size={14} strokeWidth={1.75} aria-hidden="true" />
              Add a passkey
            </Button>
          )}
        </div>

        {!browserSupportsWebAuthn() && (
          <EmptyRow>This browser does not support passkeys.</EmptyRow>
        )}
        {passkeys === null && <EmptyRow>Loading...</EmptyRow>}
        {passkeys?.length === 0 && <EmptyRow>No passkeys yet.</EmptyRow>}
        {passkeys && passkeys.length > 0 && (
          <ul className="list-none p-0 m-0">
            {passkeys.map((pk) => (
              <ListRow
                key={pk.credential_id}
                icon={KeyRound}
                label={pk.label}
                removing={removingId === pk.credential_id}
                onRemove={() => removePasskey(pk.credential_id)}
              />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="font-medium mb-2">Trusted devices</h3>
        {devices === null && <EmptyRow>Loading...</EmptyRow>}
        {devices?.length === 0 && <EmptyRow>No devices are trusted yet.</EmptyRow>}
        {devices && devices.length > 0 && (
          <ul className="list-none p-0 m-0">
            {devices.map((d) => (
              <ListRow
                key={d.device_id}
                icon={Laptop}
                label={d.label}
                removing={removingId === d.device_id}
                onRemove={() => removeDevice(d.device_id)}
              />
            ))}
          </ul>
        )}
      </section>
    </Card>
  );
}

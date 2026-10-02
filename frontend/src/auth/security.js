/**
 * Frontend surface for /auth/2fa/* and /auth/passkeys/* — device-trust email
 * verification and passwordless passkey sign-in.
 *
 * Kept separate from api/client.js's generic wrapper because two of the
 * passkey calls (`passkeyLoginOptions`, `passkeyLoginVerify`) are the only
 * requests in the whole app that must succeed with NO Firebase session — that
 * is the entire mechanism of passkey sign-in, not an edge case to route around.
 * `api`'s interceptor only ever *adds* an Authorization header when one
 * exists, so calling it signed-out already does the right thing; it is
 * flagged here so nobody "fixes" that thinking it is a bug.
 */

import api from "../api/client";

/** A short, best-effort label so a learner can tell devices apart later. */
export function guessDeviceLabel() {
  const ua = navigator.userAgent || "";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Firefox\//.test(ua)
        ? "Firefox"
        : /Safari\//.test(ua)
          ? "Safari"
          : "Browser";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS X/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return os ? `${browser} on ${os}` : browser;
}

// ------------------------------------------------------------------- 2FA

export const twoFactorEnabled = () => api.get("/auth/2fa/enabled").then((r) => r.data.enabled);

export const deviceTrustStatus = (deviceId) =>
  api.post("/auth/2fa/status", { device_id: deviceId }).then((r) => r.data.trusted);

export const sendDeviceCode = (deviceId) =>
  api.post("/auth/2fa/send", { device_id: deviceId }).then((r) => r.data);

export const verifyDeviceCode = (deviceId, code) =>
  api
    .post("/auth/2fa/verify", { device_id: deviceId, code, device_label: guessDeviceLabel() })
    .then((r) => r.data);

export const listTrustedDevices = () => api.get("/auth/devices").then((r) => r.data);

export const revokeTrustedDevice = (deviceId) =>
  api.delete(`/auth/devices/${encodeURIComponent(deviceId)}`).then((r) => r.data);

// ---------------------------------------------------------------- passkeys

export const listPasskeys = () => api.get("/auth/passkeys").then((r) => r.data);

export const revokePasskey = (credentialId) =>
  api.delete(`/auth/passkeys/${encodeURIComponent(credentialId)}`).then((r) => r.data);

export const passkeyRegisterOptions = () =>
  api.post("/auth/passkeys/register/options").then((r) => r.data);

export const passkeyRegisterVerify = (challengeId, credential, label) =>
  api
    .post("/auth/passkeys/register/verify", { challenge_id: challengeId, credential, label })
    .then((r) => r.data);

// Deliberately the plain axios instance's own request, not the interceptor's
// concern either way - these two succeed with or without a Firebase session.
export const passkeyLoginOptions = (email) =>
  api.post("/auth/passkeys/login/options", { email }).then((r) => r.data);

export const passkeyLoginVerify = (challengeId, credential) =>
  api
    .post("/auth/passkeys/login/verify", { challenge_id: challengeId, credential })
    .then((r) => r.data);

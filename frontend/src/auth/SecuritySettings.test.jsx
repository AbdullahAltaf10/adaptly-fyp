import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const webauthn = {
  startRegistration: vi.fn(),
  browserSupportsWebAuthn: vi.fn(() => true),
};

const { FakeWebAuthnError } = vi.hoisted(() => {
  class FakeWebAuthnError extends Error {
    constructor(message, cause) {
      super(message);
      this.name = "WebAuthnError";
      this.cause = cause;
    }
  }
  return { FakeWebAuthnError };
});

vi.mock("@simplewebauthn/browser", () => ({
  startRegistration: (...args) => webauthn.startRegistration(...args),
  browserSupportsWebAuthn: (...args) => webauthn.browserSupportsWebAuthn(...args),
  WebAuthnError: FakeWebAuthnError,
}));

const security = {
  listPasskeys: vi.fn(),
  listTrustedDevices: vi.fn(),
  passkeyRegisterOptions: vi.fn(),
  passkeyRegisterVerify: vi.fn(),
  revokePasskey: vi.fn(),
  revokeTrustedDevice: vi.fn(),
};
vi.mock("./security", () => ({
  guessDeviceLabel: () => "Chrome on Windows",
  listPasskeys: (...args) => security.listPasskeys(...args),
  listTrustedDevices: (...args) => security.listTrustedDevices(...args),
  passkeyRegisterOptions: (...args) => security.passkeyRegisterOptions(...args),
  passkeyRegisterVerify: (...args) => security.passkeyRegisterVerify(...args),
  revokePasskey: (...args) => security.revokePasskey(...args),
  revokeTrustedDevice: (...args) => security.revokeTrustedDevice(...args),
}));

import SecuritySettings from "./SecuritySettings";

beforeEach(() => {
  Object.values(webauthn).forEach((fn) => typeof fn.mockReset === "function" && fn.mockReset());
  Object.values(security).forEach((fn) => fn.mockReset());
  webauthn.browserSupportsWebAuthn.mockReturnValue(true);
  security.listPasskeys.mockResolvedValue([]);
  security.listTrustedDevices.mockResolvedValue([]);
});

it("shows empty states when nothing is registered yet", async () => {
  render(<SecuritySettings />);
  expect(await screen.findByText(/no passkeys yet/i)).toBeTruthy();
  expect(screen.getByText(/no devices are trusted yet/i)).toBeTruthy();
});

it("lists existing passkeys and trusted devices", async () => {
  security.listPasskeys.mockResolvedValue([{ credential_id: "c1", label: "My phone" }]);
  security.listTrustedDevices.mockResolvedValue([{ device_id: "d1", label: "Chrome on Windows" }]);
  render(<SecuritySettings />);

  expect(await screen.findByText("My phone")).toBeTruthy();
  expect(screen.getByText("Chrome on Windows")).toBeTruthy();
});

it("hides the add-passkey button when the browser does not support WebAuthn", async () => {
  webauthn.browserSupportsWebAuthn.mockReturnValue(false);
  render(<SecuritySettings />);
  await screen.findByText(/no passkeys yet/i);
  expect(screen.queryByRole("button", { name: /add a passkey/i })).toBeNull();
  expect(screen.getByText(/does not support passkeys/i)).toBeTruthy();
});

it("registering a passkey runs the full ceremony and reloads the list", async () => {
  const user = userEvent.setup();
  security.passkeyRegisterOptions.mockResolvedValue({ options: { fake: true }, challenge_id: "ch1" });
  webauthn.startRegistration.mockResolvedValue({ id: "new-cred" });
  security.passkeyRegisterVerify.mockResolvedValue({ registered: true });
  security.listPasskeys
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce([{ credential_id: "new-cred", label: "Chrome on Windows" }]);

  render(<SecuritySettings />);
  await screen.findByText(/no passkeys yet/i);

  await user.click(screen.getByRole("button", { name: /add a passkey/i }));

  await waitFor(() =>
    expect(security.passkeyRegisterVerify).toHaveBeenCalledWith("ch1", { id: "new-cred" }, "Chrome on Windows")
  );
  expect(await screen.findByText("Chrome on Windows")).toBeTruthy();
});

it("treats a cancelled passkey prompt as a non-event", async () => {
  const user = userEvent.setup();
  security.passkeyRegisterOptions.mockResolvedValue({ options: {}, challenge_id: "ch1" });
  const cancelled = new Error("cancelled");
  cancelled.name = "NotAllowedError";
  webauthn.startRegistration.mockRejectedValue(cancelled);

  render(<SecuritySettings />);
  await screen.findByText(/no passkeys yet/i);
  await user.click(screen.getByRole("button", { name: /add a passkey/i }));

  await waitFor(() => expect(webauthn.startRegistration).toHaveBeenCalled());
  expect(screen.queryByRole("alert")).toBeNull();
});

it("shows an error for a real registration failure", async () => {
  const user = userEvent.setup();
  security.passkeyRegisterOptions.mockResolvedValue({ options: {}, challenge_id: "ch1" });
  webauthn.startRegistration.mockRejectedValue(
    new FakeWebAuthnError("bad state", { name: "InvalidStateError" })
  );

  render(<SecuritySettings />);
  await screen.findByText(/no passkeys yet/i);
  await user.click(screen.getByRole("button", { name: /add a passkey/i }));

  expect(await screen.findByRole("alert")).toBeTruthy();
});

it("removing a passkey calls revoke and reloads", async () => {
  const user = userEvent.setup();
  security.listPasskeys
    .mockResolvedValueOnce([{ credential_id: "c1", label: "My phone" }])
    .mockResolvedValueOnce([]);
  security.revokePasskey.mockResolvedValue({ revoked: true });

  render(<SecuritySettings />);
  await screen.findByText("My phone");

  await user.click(screen.getByRole("button", { name: /remove/i }));

  await waitFor(() => expect(security.revokePasskey).toHaveBeenCalledWith("c1"));
  await waitFor(() => expect(screen.getByText(/no passkeys yet/i)).toBeTruthy());
});

it("removing a trusted device calls revoke and reloads", async () => {
  const user = userEvent.setup();
  security.listTrustedDevices
    .mockResolvedValueOnce([{ device_id: "d1", label: "Old laptop" }])
    .mockResolvedValueOnce([]);
  security.revokeTrustedDevice.mockResolvedValue({ revoked: true });

  render(<SecuritySettings />);
  await screen.findByText("Old laptop");

  await user.click(screen.getByRole("button", { name: /remove/i }));

  await waitFor(() => expect(security.revokeTrustedDevice).toHaveBeenCalledWith("d1"));
  await waitFor(() => expect(screen.getByText(/no devices are trusted yet/i)).toBeTruthy());
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navigateSpy = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => navigateSpy };
});

const security = {
  sendDeviceCode: vi.fn(),
  verifyDeviceCode: vi.fn(),
};
vi.mock("./security", () => ({
  sendDeviceCode: (...args) => security.sendDeviceCode(...args),
  verifyDeviceCode: (...args) => security.verifyDeviceCode(...args),
  guessDeviceLabel: () => "Test browser",
}));

vi.mock("./deviceId", () => ({ getDeviceId: () => "device-123" }));

const refreshDeviceTrust = vi.fn();
vi.mock("./AuthContext", () => ({
  useAuth: () => ({
    currentUser: { email: "learner@test.com" },
    refreshDeviceTrust,
  }),
}));

import VerifyDevicePage from "./VerifyDevicePage";

const draw = () =>
  render(
    <MemoryRouter>
      <VerifyDevicePage />
    </MemoryRouter>
  );

beforeEach(() => {
  navigateSpy.mockReset();
  refreshDeviceTrust.mockReset().mockResolvedValue();
  security.sendDeviceCode.mockReset();
  security.verifyDeviceCode.mockReset();
});

it("starts with only the send-code action visible", () => {
  draw();
  expect(screen.getByRole("button", { name: /email me a code/i })).toBeTruthy();
  expect(screen.queryByLabelText(/verification code/i)).toBeNull();
});

it("reveals the code form once a code has been sent", async () => {
  const user = userEvent.setup();
  security.sendDeviceCode.mockResolvedValue({ sent: true });
  draw();

  await user.click(screen.getByRole("button", { name: /email me a code/i }));

  expect(await screen.findByLabelText(/verification code/i)).toBeTruthy();
  expect(security.sendDeviceCode).toHaveBeenCalledWith("device-123");
});

it("verifying the correct code trusts the device and continues into the app", async () => {
  const user = userEvent.setup();
  security.sendDeviceCode.mockResolvedValue({ sent: true });
  security.verifyDeviceCode.mockResolvedValue({ trusted: true });
  draw();

  await user.click(screen.getByRole("button", { name: /email me a code/i }));
  await user.type(await screen.findByLabelText(/verification code/i), "123456");
  await user.click(screen.getByRole("button", { name: /verify and continue/i }));

  await waitFor(() => expect(security.verifyDeviceCode).toHaveBeenCalledWith("device-123", "123456"));
  await waitFor(() => expect(refreshDeviceTrust).toHaveBeenCalled());
  await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith("/", { replace: true }));
});

it("shows the server's message when the code is wrong, and does not navigate", async () => {
  const user = userEvent.setup();
  security.sendDeviceCode.mockResolvedValue({ sent: true });
  security.verifyDeviceCode.mockRejectedValue({
    response: { data: { detail: "That code is incorrect." } },
  });
  draw();

  await user.click(screen.getByRole("button", { name: /email me a code/i }));
  await user.type(await screen.findByLabelText(/verification code/i), "000000");
  await user.click(screen.getByRole("button", { name: /verify and continue/i }));

  expect(await screen.findByText("That code is incorrect.")).toBeTruthy();
  expect(navigateSpy).not.toHaveBeenCalled();
});

it("only accepts digits, capped at 6", async () => {
  const user = userEvent.setup();
  security.sendDeviceCode.mockResolvedValue({ sent: true });
  draw();
  await user.click(screen.getByRole("button", { name: /email me a code/i }));

  const input = await screen.findByLabelText(/verification code/i);
  await user.type(input, "12ab3456789");
  expect(input.value).toBe("123456");
});

it("disables verify until 6 digits are entered", async () => {
  const user = userEvent.setup();
  security.sendDeviceCode.mockResolvedValue({ sent: true });
  draw();
  await user.click(screen.getByRole("button", { name: /email me a code/i }));

  const verifyButton = screen.getByRole("button", { name: /verify and continue/i });
  expect(verifyButton).toBeDisabled();

  await user.type(await screen.findByLabelText(/verification code/i), "12345");
  expect(verifyButton).toBeDisabled();
});

it("explains when the email service is not configured", async () => {
  const user = userEvent.setup();
  security.sendDeviceCode.mockRejectedValue({ response: { status: 503 } });
  draw();

  await user.click(screen.getByRole("button", { name: /email me a code/i }));

  expect(await screen.findByText(/not set up yet/i)).toBeTruthy();
});

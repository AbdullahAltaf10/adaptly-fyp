/**
 * A separate file from StudySession.test.jsx on purpose: this one mounts
 * the REAL AssistantPanel (not mocked) against a rejecting API client, to
 * prove a failed assistant request cannot take the rest of the study
 * screen down with it. Everything else it needs mocked stays the same as
 * StudySession.test.jsx's mocks.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../engagement/useEngagementCapture", () => ({
  useEngagementCapture: () => ({
    videoRef: { current: null },
    ready: true,
    calibrated: false,
    calibrating: false,
    calibrationError: null,
    runCalibration: vi.fn(),
    faceDetected: false,
    status: "Ready",
    framesCollected: 0,
    windowSize: 10,
    lightingWarning: null,
    droppedWindows: 0,
    prediction: null,
    sessionId: "live-session-123",
  }),
}));
vi.mock("../engagement/useFacePresence", () => ({
  useFacePresence: () => ({
    faceLost: false,
    showTick: false,
    suggestRecalibrate: false,
    dismissRecalibrate: vi.fn(),
  }),
}));
vi.mock("../intervention/useDwell", () => ({
  useDwell: () => ({ seconds: () => 0, register: vi.fn() }),
}));
vi.mock("../intervention/useIntervention", () => ({
  useIntervention: () => ({
    current: null,
    content: null,
    loading: false,
    accepted: false,
    accept: vi.fn(),
    complete: vi.fn(),
    dismiss: vi.fn(),
  }),
}));
vi.mock("../api/client", () => ({
  default: { post: vi.fn(() => Promise.reject(new Error("network"))) },
}));

import StudySession from "./StudySession";

describe("StudySession — assistant panel survives an API error", () => {
  it("shows a safe error in the panel and leaves the rest of the study screen usable", async () => {
    render(<StudySession contentId="content-1" chunkId="chunk-1" />);
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));
    fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));

    fireEvent.change(screen.getByLabelText("Ask Adaptly a question"), {
      target: { value: "What does this mean?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    // The rest of the study screen is untouched by the failed request.
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /close assistant/i })).toBeInTheDocument();
  });
});

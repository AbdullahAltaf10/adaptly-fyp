/**
 * Tests for mounting the Module 5 assistant panel in the study session
 * screen (Issue: "Render the assistant panel in the study session screen").
 *
 * Every engagement/intervention hook is mocked: this file is about the
 * assistant wiring, not re-testing Module 3/4's own hooks (already covered
 * by their own test files).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const baseCapture = {
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
};

vi.mock("../engagement/useEngagementCapture", () => ({
  useEngagementCapture: () => baseCapture,
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

// `useContent` sits on top of `../api/client`, which pulls in Firebase auth --
// not available in this test environment, and not what this file is testing.
// Default to "no document" so the existing fallback-context tests keep their
// original meaning; the real-chunk-text test below overrides this per-case.
let mockContent = { content: null, loading: false, error: null };
vi.mock("../content/useContent", () => ({
  useContent: () => mockContent,
}));

// Scope 6.2's pre-session camera check is not what this file tests, and a
// real getUserMedia probe never resolves "ready" in jsdom, which would
// leave "Start session" permanently disabled here.
vi.mock("../engagement/usePreSessionCheck", () => ({
  CAMERA_UNKNOWN: "unknown",
  CAMERA_OK: "ok",
  CAMERA_DENIED: "denied",
  CAMERA_MISSING: "missing",
  CAMERA_FAILED: "failed",
  usePreSessionCheck: () => ({
    videoRef: { current: null },
    checking: false,
    camera: "ok",
    cameraReady: true,
    brightness: 120,
    lowLight: false,
    recheck: vi.fn(),
  }),
}));

const capturedProps = [];
vi.mock("../features/ai-assistant/AssistantPanel", () => ({
  AssistantPanel: (props) => {
    capturedProps.push(props);
    return <div data-testid="assistant-panel">assistant panel mounted</div>;
  },
}));

import { fallbackStudyContext } from "../features/ai-assistant/demoStudyContext";
import StudySession from "./StudySession";

function startSession() {
  fireEvent.click(screen.getByRole("button", { name: /start session/i }));
}

describe("StudySession — assistant panel", () => {
  beforeEach(() => {
    capturedProps.length = 0;
    mockContent = { content: null, loading: false, error: null };
  });

  it("does not offer the assistant before a session has started", () => {
    render(<StudySession contentId="content-1" chunkId="chunk-1" />);
    expect(screen.queryByRole("button", { name: /ask the assistant/i })).not.toBeInTheDocument();
  });

  it("is collapsed by default once a session starts, and toggles open/closed", () => {
    render(<StudySession contentId="content-1" chunkId="chunk-1" />);
    startSession();

    expect(screen.queryByTestId("assistant-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));
    expect(screen.getByTestId("assistant-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close assistant/i }));
    expect(screen.queryByTestId("assistant-panel")).not.toBeInTheDocument();
  });

  it("passes the real live session_id, content_id, and chunk_id as context", () => {
    render(<StudySession contentId="content-42" chunkId="chunk-7" />);
    startSession();
    fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));

    const context = capturedProps.at(-1).studyContext;
    expect(context.session_id).toBe("live-session-123");
    expect(context.content_id).toBe("content-42");
    expect(context.current_chunk.chunk_id).toBe("chunk-7");
  });

  it("falls back to placeholder context fields when no document is loaded", () => {
    render(<StudySession contentId="content-42" chunkId="chunk-7" />);
    startSession();
    fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));

    const context = capturedProps.at(-1).studyContext;
    // No document is loaded in this case -- these must still be present
    // (from the fallback shape), not undefined, so AssistantPanel never
    // receives a malformed context object.
    expect(context.current_chunk.text).toEqual(expect.any(String));
    expect(context.content_context).toBeDefined();
  });

  it("passes the real chunk text and content metadata from ContentViewer's document, not the fallback placeholder", () => {
    mockContent = {
      loading: false,
      error: null,
      content: {
        content_id: "content-42",
        title: "Gradient Descent, Explained",
        content_type: "pdf",
        language: "en",
        chunks: [
          {
            chunk_id: "chunk-7",
            order: 1,
            section_title: "Step Sizes",
            text: "A learning rate that is too large can overshoot the minimum.",
          },
        ],
      },
    };

    render(<StudySession contentId="content-42" chunkId="chunk-7" />);
    startSession();
    fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));

    const context = capturedProps.at(-1).studyContext;
    expect(context.current_chunk.chunk_id).toBe("chunk-7");
    expect(context.current_chunk.text).toBe(
      "A learning rate that is too large can overshoot the minimum."
    );
    expect(context.current_chunk.section_title).toBe("Step Sizes");
    expect(context.current_chunk.text).not.toBe(fallbackStudyContext.current_chunk.text);

    expect(context.content_context).toEqual({
      title: "Gradient Descent, Explained",
      content_type: "pdf",
      language: "en",
    });
    expect(context.content_context).not.toEqual(fallbackStudyContext.content_context);
  });

  it("keeps the rest of the study screen intact if mounting/toggling the assistant is exercised repeatedly", () => {
    render(<StudySession contentId="content-1" chunkId="chunk-1" />);
    startSession();

    const toggle = screen.getByRole("button", { name: /ask the assistant/i });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /close assistant/i }));
    fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));

    // The engagement status line (unrelated to the assistant) is still
    // there and unaffected by any of the above.
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });
});

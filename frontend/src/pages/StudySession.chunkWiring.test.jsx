/**
 * Which chunk a window and the assistant are told about.
 *
 * This wiring was broken once: `dwell.chunkId` is a getter, and the page used
 * it as if it were the chunk id, so no window ever carried a chunk and the
 * assistant was never handed the paragraph on screen. The other StudySession
 * tests mock `useDwell` without a chunk, which is exactly why nothing failed.
 * This file mocks it the way the real hook actually looks.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Floating UI's real autoUpdate() relies on ResizeObserver/RAF plumbing
// jsdom does not provide, which hangs/crashes a test run (ParagraphPopup
// renders for real here, via the real StudySession) rather than failing it
// cleanly. See ParagraphPopup.test.jsx for the same mock and rationale.
vi.mock("@floating-ui/dom", () => ({
  computePosition: () => Promise.resolve({ x: 0, y: 0, placement: "right-start" }),
  autoUpdate: () => () => {},
  offset: () => ({}),
  flip: () => ({}),
  shift: () => ({}),
}));

const captureArgs = [];
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
  endSessionNow: () => Promise.resolve({}),
};

vi.mock("../engagement/useEngagementCapture", () => ({
  useEngagementCapture: (args) => {
    captureArgs.push(args);
    return baseCapture;
  },
}));
vi.mock("../engagement/useFacePresence", () => ({
  useFacePresence: () => ({
    faceLost: false,
    showTick: false,
    suggestRecalibrate: false,
    dismissRecalibrate: vi.fn(),
  }),
}));

const chunkGetter = () => "1";
vi.mock("../intervention/useDwell", () => ({
  useDwell: () => ({
    seconds: () => 0,
    register: vi.fn(),
    chunkId: chunkGetter,
    activeChunkId: "1",
    // The real useDwell (Task 5) always provides this; matching its shape
    // here lets useDwellFusion's real, un-shimmed fusion logic run against
    // this mock instead of needing a special case for an unrealistic one.
    visibilityRatios: () => new Map([["1", 1]]),
  }),
}));
const useInterventionMock = vi.fn(() => ({
  current: null,
  content: null,
  loading: false,
  accepted: false,
  accept: vi.fn(),
  complete: vi.fn(),
  dismiss: vi.fn(),
}));
vi.mock("../intervention/useIntervention", () => ({
  useIntervention: () => useInterventionMock(),
}));

const mockContent = {
  content: {
    title: "Handbook",
    content_type: "pdf",
    language: "en",
    chunks: [
      { chunk_id: "0", order: 0, text: "First paragraph text." },
      { chunk_id: "1", order: 1, text: "Second paragraph text.", section_title: "Part two" },
    ],
  },
  loading: false,
  error: null,
};
vi.mock("../content/useContent", () => ({ useContent: () => mockContent }));
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

const assistantProps = [];
vi.mock("../features/ai-assistant/AssistantPanel", () => ({
  AssistantPanel: (props) => {
    assistantProps.push(props);
    return <div data-testid="assistant-panel" />;
  },
}));

import StudySession from "./StudySession";

beforeEach(() => {
  captureArgs.length = 0;
  assistantProps.length = 0;
  useInterventionMock.mockClear();
});

function startAndOpenAssistant() {
  render(
    <MemoryRouter>
      <StudySession contentId="content-1" />
    </MemoryRouter>
  );
  fireEvent.click(screen.getByRole("button", { name: /start session/i }));
  fireEvent.click(screen.getByRole("button", { name: /ask the assistant/i }));
}

describe("StudySession: chunk wiring", () => {
  it("hands the capture loop the chunk GETTER, not a value", () => {
    render(
      <MemoryRouter>
        <StudySession contentId="content-1" />
      </MemoryRouter>
    );
    const latest = captureArgs[captureArgs.length - 1];
    // A function, called at send time - not the raw useDwell getter's own
    // identity, since useDwellFusion now sits between useDwell and this
    // call and necessarily wraps it in its own closure. What must hold is
    // behavioral, not referential: it is a function, and calling it returns
    // what the underlying chunk getter reports.
    expect(typeof latest.getChunkId).toBe("function");
    expect(latest.getChunkId()).toBe(chunkGetter());
  });

  it("never passes a function as the fallback chunk id", () => {
    render(
      <MemoryRouter>
        <StudySession contentId="content-1" chunkId="pinned" />
      </MemoryRouter>
    );
    const latest = captureArgs[captureArgs.length - 1];
    expect(latest.chunkId).toBe("pinned");
    expect(typeof latest.chunkId).not.toBe("function");
  });

  it("tells the assistant about the paragraph actually on screen", () => {
    startAndOpenAssistant();
    const { studyContext } = assistantProps[assistantProps.length - 1];
    expect(studyContext.current_chunk.chunk_id).toBe("1");
    expect(studyContext.current_chunk.text).toBe("Second paragraph text.");
    expect(studyContext.current_chunk.section_title).toBe("Part two");
  });

  it("anchors the popup to the chunk the intervention is actually about, not wherever the page happens to render it", async () => {
    // mockContent (this file's existing fixture, lines 74-86) has chunks
    // "0" and "1"; the useDwell mock (lines 50-61) fixes activeChunkId to
    // "1" - this intervention is deliberately for chunk "1" too, so the
    // popup's anchoring can be checked against the real registered element.
    useInterventionMock.mockReturnValue({
      current: { intervention_id: "int-1", chunk_id: "1" },
      content: { generated: "Simplified.", original: "Second paragraph text." },
      loading: false,
      accepted: false,
      accept: vi.fn(),
      complete: vi.fn(),
      dismiss: vi.fn(),
    });
    const { container } = render(
      <MemoryRouter>
        <StudySession contentId="content-1" />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));
    expect(screen.getByText("Simplified.")).toBeInTheDocument();
    // Anchored (fixed), not the unpositioned bottom-of-flow fallback: proves
    // chunkElementsRef actually resolved a real DOM element for chunk "1".
    // ParagraphPopup renders this content either way (its own fallback for a
    // missing chunkElement, per its own tests) - position is what actually
    // distinguishes correct wiring from a silently-null chunkElement here.
    // ".shadow-floating" is unique to ParagraphPopup - several other cards on
    // this page (e.g. the camera setup card) also use ".rounded-card".
    const popupCard = container.querySelector(".shadow-floating");
    await waitFor(() => expect(popupCard).toHaveStyle({ position: "fixed" }));
  });
});

/**
 * Study session screen.
 *
 * All camera and inference behaviour lives in `src/engagement/`. This file is
 * rendering and copy only, so the capture loop can be reasoned about (and
 * reused by Module 4) without reading through layout code.
 *
 * The diagnostics panel at the bottom is a development instrument. Scope
 * section 6.8 requires that no scores or state indicators are shown during an
 * active session in the finished product, so this panel comes out before any
 * learner-facing release.
 */

import { AlertTriangle, Bot, Camera, CheckCircle2, CircleDashed, X } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AssistantPanel } from "../features/ai-assistant/AssistantPanel";
import { fallbackStudyContext } from "../features/ai-assistant/demoStudyContext";
import ContentViewer from "../content/ContentViewer";
import { useContent } from "../content/useContent";
import PreSessionCheck from "../engagement/PreSessionCheck";
import { useEngagementCapture } from "../engagement/useEngagementCapture";
import { useFacePresence } from "../engagement/useFacePresence";
import { usePreSessionCheck } from "../engagement/usePreSessionCheck";
import InterventionHost from "../intervention/InterventionHost";
import ParagraphPopup from "../intervention/ParagraphPopup";
import { needsGeneratedText } from "../intervention/constants";
import { useDwellFusion } from "../intervention/useDwellFusion";
import { useIntervention } from "../intervention/useIntervention";
import { useParagraphPopup } from "../intervention/useParagraphPopup";
import { Button } from "../ui";

/**
 * How a reported state is labelled - developer diagnostics only.
 *
 * Scope 6.8: "No statistics, scores, or indicators are shown during an active
 * session." This state label is exactly that indicator, so it lives inside
 * the collapsed Diagnostics disclosure below, never in the learner's own
 * view. It used to also render unconditionally in the main flow, in colour,
 * which was the scope violation this redesign removes.
 */
const STATE_DISPLAY = {
  focused: { label: "Focused" },
  drifting: { label: "Drifting" },
  struggling: { label: "Struggling" },
  fatigued: { label: "Fatigued" },
  recovered: { label: "Recovered" },
};

function describeState(state) {
  return STATE_DISPLAY[state] ?? { label: state ?? "Unknown" };
}

export default function StudySession({ contentId, chunkId }) {
  const navigate = useNavigate();
  const [started, setStarted] = useState(false);
  const [ending, setEnding] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);

  const document_ = useContent(contentId);

  // Scope 6.2's pre-session check. Runs only while the dialog is up, and
  // releases its probe stream before the session's own camera is requested.
  const preSession = usePreSessionCheck({ enabled: !started });

  // `ContentViewer` calls `dwell.register(chunk_id, element)` for every chunk
  // it renders (issue #47), so the most-visible chunk and how long it has been
  // read are both real numbers now. Before this, nothing registered, dwell
  // stayed 0, and `simplify_content` and `bullet_summary` could never be
  // offered however long someone stared at a hard paragraph.
  // `capture` (below) needs `dwell.chunkId`/`dwell.seconds`, and dwell fusion
  // needs `capture.getLatestLandmarks` for its gaze-quadrant signal - each
  // hook needs the other's result. Resolved with a stable ref bridge: the
  // getter's identity never changes (so the fusion interval below is never
  // torn down and recreated on a render), but it always reads whatever
  // `capture` most recently was.
  const captureRef = useRef(null);
  const getLatestLandmarksBridge = useCallback(
    () => captureRef.current?.getLatestLandmarks?.() ?? null,
    []
  );
  const dwell = useDwellFusion({ enabled: started, getLatestLandmarks: getLatestLandmarksBridge });

  // useDwellFusion's internal element map is not exposed, so ParagraphPopup
  // (which needs the actual DOM element for the intervention's own chunk_id
  // to anchor to) is served from this small parallel map instead, populated
  // through the same onChunkRef callback ContentViewer already calls for
  // every chunk.
  const chunkElementsRef = useRef(new Map()); // chunk_id -> DOM element
  // Depends on dwell.register specifically, not the whole `dwell` object:
  // useDwellFusion returns a fresh object literal every render (see its own
  // comment on the analogous issue for its internal `register`), so
  // depending on it directly would give this callback a new identity every
  // render - which would give ContentChunk's ref callback a new identity too
  // (it depends on onChunkRef), causing React to unregister and re-register
  // every chunk on every render and never let useDwell's IntersectionObserver
  // report a stable visibility ratio. dwell.register itself is stable.
  const registerChunkElement = useCallback((chunkId, element) => {
    dwell.register(chunkId, element);
    if (element) {
      chunkElementsRef.current.set(chunkId, element);
    } else {
      chunkElementsRef.current.delete(chunkId);
    }
  }, [dwell.register]);

  // The chunk the learner is actually on beats whatever was passed in. The
  // prop stays as the fallback for a session with no document (the camera-only
  // path this page started as), and so the caller can pin a chunk in a test.
  //
  // `dwell.activeChunkId` is the render-time VALUE (used below to find the
  // paragraph for the assistant). `dwell.chunkId` is a GETTER, handed to the
  // capture loop so each window carries the chunk it was captured on. This
  // line used to read `dwell.chunkId ?? chunkId`, which is the getter itself -
  // always truthy - so `activeChunkId` was a function, no window ever carried
  // a chunk id, and everything keyed on one (the passage an intervention
  // rewrites, the critical-section flag, per-chunk analytics) silently got
  // nothing. The tests hid it because they mock this hook without a chunkId.
  const activeChunkId = dwell.activeChunkId ?? chunkId;

  const capture = useEngagementCapture({
    active: started,
    contentId,
    chunkId,
    getChunkId: dwell.chunkId,
    getDwellSeconds: dwell.seconds,
  });
  captureRef.current = capture;

  // Until this existed, a session only ended when the whole page unmounted -
  // navigating away, or closing the tab (the `pagehide` handler inside
  // useEngagementCapture covers that second case; before it, that lost the
  // session's analytics entirely). Awaiting the real call before navigating
  // means the learner lands on their analytics after the backend has actually
  // finalized the session, not while it is still in flight.
  const endSession = async () => {
    setEnding(true);
    try {
      await capture.endSessionNow();
    } catch {
      // Best effort - finalization is failure-safe on the backend regardless,
      // and staying on this screen forever over a network blip would be
      // worse than moving on and letting the learner check back later.
    } finally {
      setStarted(false);
      navigate(`/analytics?session=${encodeURIComponent(capture.sessionId)}`);
    }
  };

  const presence = useFacePresence({
    faceDetected: capture.faceDetected,
    enabled: started && capture.ready,
    calibrated: capture.calibrated,
  });

  // Module 4. `prediction.intervention` is null on almost every window - the
  // cooldown alone keeps it empty for two minutes after anything fires.
  const intervention = useIntervention({
    intervention: capture.prediction?.intervention ?? null,
    sessionId: capture.sessionId,
  });

  const popup = useParagraphPopup({ intervention, activeChunkId: dwell.activeChunkId });

  // What the sticky AssistantPanel is seeded with when the learner clicks
  // "Continue in chat" on the popup - the panel appends this once (gated on
  // its own id, see AssistantPanel.jsx) and further questions continue
  // there, in the same persistent history the popup's own content was
  // already written to (source="popup", Task 4).
  const [assistantSeedTurn, setAssistantSeedTurn] = useState(null);
  const continueInChat = () => {
    if (!popup.current || !popup.content?.generated) return;
    setAssistantSeedTurn({ id: popup.current.intervention_id, content: popup.content.generated });
    setAssistantOpen(true);
  };

  const { prediction } = capture;
  const diagnostics = prediction?.diagnostics ?? null;
  const display = describeState(prediction?.state);
  const deepThinking = diagnostics?.deep_thinking?.deep_thinking;

  // Module 5. `document_.content` now comes from the real ContentViewer
  // (issue #47), so the active chunk's real text/section_title and the
  // document's real title/content_type/language are available here and no
  // longer need to come from fallbackStudyContext. Only pieces the document
  // genuinely doesn't have (learner_preferences, and the chunk/content shape
  // when no document is loaded at all) still fall back to the placeholder.
  const activeChunk = useMemo(
    () =>
      document_.content?.chunks?.find((chunk) => chunk.chunk_id === activeChunkId) ?? null,
    [document_.content, activeChunkId]
  );

  const studyContext = useMemo(
    () => ({
      ...fallbackStudyContext,
      session_id: capture.sessionId ?? fallbackStudyContext.session_id,
      content_id: contentId ?? fallbackStudyContext.content_id,
      current_chunk: activeChunk
        ? {
            chunk_id: activeChunk.chunk_id,
            section_title: activeChunk.section_title ?? null,
            text: activeChunk.text,
          }
        : {
            ...fallbackStudyContext.current_chunk,
            chunk_id: activeChunkId ?? fallbackStudyContext.current_chunk.chunk_id,
          },
      content_context: document_.content
        ? {
            title: document_.content.title,
            content_type: document_.content.content_type,
            language: document_.content.language,
          }
        : fallbackStudyContext.content_context,
      session_context: {
        ...fallbackStudyContext.session_context,
        status: started ? "active" : fallbackStudyContext.session_context.status,
        current_chunk_id: activeChunkId ?? fallbackStudyContext.session_context.current_chunk_id,
      },
    }),
    [capture.sessionId, contentId, activeChunk, activeChunkId, started, document_.content]
  );


  // Enlarging the camera view must not move the <video> element in the React
  // tree: remounting it drops srcObject and the picture goes black.
  const videoWrapClass = presence.faceLost
    ? "fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[950] flex flex-col items-center"
    : "relative flex flex-col items-center mb-3";

  return (
    <div>
      {/* Keyframes cannot be expressed as inline styles. */}
      <style>{`
        @keyframes adaptly-draw  { to { stroke-dashoffset: 0; } }
        @keyframes adaptly-pop   { from { transform: scale(.6); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        @keyframes adaptly-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .55; } }
      `}</style>

      {/* Always visible once a session is running - the one control this
          screen was missing entirely. Fixed at the top so it is reachable
          without scrolling past the video or the document, and it is the
          only reliable way a learner ends a session on purpose: without it,
          the session only ever closed by leaving the page, and a learner who
          simply left their tab open never generated an analytics summary,
          an insight report, or (for a corporate account) a compliance report
          at all - finalization only ever runs at session end. */}
      {started && (
        <div className="sticky top-0 z-[850] flex justify-end px-4 py-2 bg-surface/95 backdrop-blur-sm border-b border-line">
          <Button variant="secondary" busy={ending} busyLabel="Ending session..." onClick={endSession}>
            End session
          </Button>
        </div>
      )}

      {/* The session's own camera is not requested until this is dismissed.
          The check below opens a short-lived probe stream of its own and stops
          it again, so the two never share a stream. */}
      {!started && (
        <PreSessionCheck
          check={preSession}
          warnings={document_.content?.warnings ?? []}
          document={contentId ? { loading: document_.loading, error: document_.error } : undefined}
          onStart={() => setStarted(true)}
        />
      )}

      {/* Dim everything behind the enlarged view so the instruction is
          unmissable while the learner is out of frame. */}
      {presence.faceLost && <div className="fixed inset-0 z-[900] bg-black/60" />}

      <div className="flex flex-col items-center text-center max-w-[760px] mx-auto px-4">
        <div className={videoWrapClass}>
          <video
            ref={capture.videoRef}
            autoPlay
            playsInline
            muted
            className={`rounded-xl border-[3px] transition-[width,border-color] duration-200 ease-out ${
              started ? "block" : "hidden"
            } ${presence.faceLost ? "w-[min(86vw,640px)] border-warning" : "w-[min(90vw,400px)] border-transparent"}`}
            style={{ transform: "scaleX(-1)" }} // mirrored, so moving left feels like left
          />

          {presence.faceLost && (
            <div className="mt-3 text-white">
              <p className="text-lg m-0 animate-[adaptly-pulse_1.4s_ease-in-out_infinite]">
                Move back into the frame
              </p>
              <p className="text-sm opacity-80 mt-1.5 m-0">Centre your face in the view above</p>
            </div>
          )}

          {presence.showTick && (
            <div aria-live="polite" className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <svg
                viewBox="0 0 52 52"
                width="110"
                height="110"
                style={{ animation: "adaptly-pop .5s ease-out both" }}
              >
                <circle
                  cx="26"
                  cy="26"
                  r="24"
                  fill="none"
                  stroke="var(--color-success)"
                  strokeWidth="3"
                  style={{
                    strokeDasharray: 151,
                    strokeDashoffset: 151,
                    animation: "adaptly-draw .9s ease-out forwards",
                  }}
                />
                <path
                  d="M14 27 l8 8 l16 -16"
                  fill="none"
                  stroke="var(--color-success)"
                  strokeWidth="4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{
                    strokeDasharray: 48,
                    strokeDashoffset: 48,
                    animation: "adaptly-draw .6s .8s ease-out forwards",
                  }}
                />
              </svg>
            </div>
          )}
        </div>

        {presence.suggestRecalibrate && !presence.faceLost && (
          <div className="flex items-center justify-center flex-wrap gap-2 px-3 py-2 mb-3 rounded-md
                          border border-warning/40 bg-warning-soft text-ink text-sm">
            <span className="flex items-center gap-1.5">
              <AlertTriangle size={14} strokeWidth={1.75} className="text-warning shrink-0" aria-hidden="true" />
              You were away for a moment. If you moved or changed seat, recalibrate.
            </span>
            <span className="flex gap-2 whitespace-nowrap">
              <Button
                variant="secondary"
                onClick={capture.runCalibration}
                disabled={!capture.ready || capture.calibrating}
              >
                Recalibrate
              </Button>
              <Button variant="quiet" onClick={presence.dismissRecalibrate}>
                Dismiss
              </Button>
            </span>
          </div>
        )}

        <div className="w-full max-w-[620px] rounded-card border border-line bg-surface shadow-card p-4 mb-4 text-left">
          <div className="flex items-center gap-2 text-sm text-ink">
            <Camera size={16} strokeWidth={1.75} className="text-muted shrink-0" aria-hidden="true" />
            {capture.status}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted mt-1">
            {capture.faceDetected ? (
              <CheckCircle2 size={14} strokeWidth={1.75} className="text-success shrink-0" aria-hidden="true" />
            ) : (
              <CircleDashed size={14} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
            )}
            Face detected: {capture.faceDetected ? "Yes" : "No"} · Frames: {capture.framesCollected} /{" "}
            {capture.windowSize}
          </div>
          {capture.lightingWarning && (
            <p className="flex items-center gap-1.5 text-warning text-xs mt-2 mb-0">
              <AlertTriangle size={14} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
              {capture.lightingWarning}
            </p>
          )}

          <div className="flex items-center gap-2 mt-3">
            <Button
              variant="secondary"
              onClick={capture.runCalibration}
              disabled={!capture.ready || capture.calibrating}
            >
              {capture.calibrating ? "Calibrating..." : capture.calibrated ? "Recalibrate" : "Calibrate now"}
            </Button>
            {capture.calibrating && <span className="text-xs text-muted">Look naturally at the screen...</span>}
            {capture.calibrated && !capture.calibrating && (
              <span className="flex items-center gap-1 text-xs text-success font-medium">
                <CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" />
                Calibrated
              </span>
            )}
          </div>
          {capture.calibrationError && (
            <p className="text-danger text-xs mt-2 mb-0">Calibration failed: {capture.calibrationError}</p>
          )}

          {/* Two waits happen before a state can appear: the window filling at
              one frame per second, and the first prediction, which loads
              TensorFlow. The backend warms the model on startup, so the second is
              usually over before anyone reaches this screen. */}
          {started && !prediction && (
            <div className="mt-3 min-h-14">
              <p className="text-sm text-muted m-0 font-medium">
                {capture.framesCollected < capture.windowSize
                  ? `Getting ready — ${capture.windowSize - capture.framesCollected}s`
                  : "Analysing your first reading..."}
              </p>
              <div className="h-1 w-full max-w-64 mt-2 bg-page rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent transition-[width] duration-300 ease-out"
                  style={{ width: `${Math.min(100, (capture.framesCollected / capture.windowSize) * 100)}%` }}
                />
              </div>
            </div>
          )}

          {/* Scope 6.8: no state, score or confidence is shown to the
              learner during a session. This lives behind the collapsed
              Diagnostics disclosure only. */}
          {prediction && diagnostics && (
            <Diagnostics
              diagnostics={diagnostics}
              dropped={capture.droppedWindows}
              state={display.label}
              confidence={prediction.confidence}
              deepThinking={deepThinking}
            />
          )}
        </div>

        {/* What the learner is here to read. Above the support, so an offer
            appears under the text it is about rather than pushing it down. */}
        {contentId && (
          <div className="w-full max-w-[620px] text-left">
            {document_.loading && <p className="text-muted">Loading the document...</p>}
            {document_.error && <p className="text-danger">{document_.error}</p>}
            {document_.content && (
              <ContentViewer
                content={document_.content}
                onChunkRef={registerChunkElement}
                activeChunkId={dwell.activeChunkId}
                fusionConfidence={dwell.fusionConfidence}
              />
            )}
          </div>
        )}

        {/* Module 4's support. simplify_content/bullet_summary are
            paragraph-anchored (ParagraphPopup, beside the paragraph they are
            about); break_suggestion/assistant_help_prompt are not, and keep
            the original bottom-of-page, inline-and-quiet card. Scope 6.4
            asks for this "without any sound, flash, or alert" either way. */}
        {intervention.current && !needsGeneratedText(intervention.current.intervention_type) && (
          <div className="w-full max-w-[620px]">
            <InterventionHost
              intervention={intervention.current}
              content={intervention.content}
              loading={intervention.loading}
              accepted={intervention.accepted}
              onAccept={intervention.accept}
              onComplete={intervention.complete}
              onDismiss={intervention.dismiss}
            />
          </div>
        )}

        <ParagraphPopup
          chunkElement={popup.current ? chunkElementsRef.current.get(popup.current.chunk_id) : null}
          intervention={popup.current}
          content={popup.content}
          collapsed={popup.collapsed}
          onToggleCollapsed={popup.toggleCollapsed}
          onComplete={popup.complete}
          onDismiss={popup.dismiss}
          onContinueInChat={continueInChat}
        />
      </div>

      {/* Module 5, as a sticky floating widget - the same idea as a
          "chat with an assistant" bubble that stays anchored to the corner of
          the screen through everything else happening on the page (Coursera's
          own AI panel is the reference point). Fixed-position and collapsed
          by default so it never moves or resizes anything above - the
          engagement/intervention layout is untouched either way. Only offered
          once a session is running, since studyContext.session_id only means
          anything at that point.
          The launcher button IS the close button once open (one control, two
          jobs) rather than a separate X inside the panel - one less thing to
          find, and it is where the eye already is. */}
      {started && (
        <div className="fixed bottom-4 right-4 z-[800] flex flex-col items-end gap-3">
          {assistantOpen && (
            <div
              className="w-[min(90vw,380px)] h-[min(70vh,32rem)] rounded-card shadow-floating
                         border border-line bg-surface overflow-hidden origin-bottom-right
                         animate-[adaptly-pop_var(--duration-base)_var(--ease-standard)_both]"
            >
              <AssistantPanel studyContext={studyContext} seedTurn={assistantSeedTurn} />
            </div>
          )}
          <button
            type="button"
            onClick={() => setAssistantOpen((open) => !open)}
            aria-expanded={assistantOpen}
            className="inline-flex items-center justify-center w-14 h-14 rounded-full
                       bg-accent text-on-accent shadow-floating hover:bg-accent-hover
                       transition-colors duration-150"
          >
            {assistantOpen ? (
              <X size={22} strokeWidth={1.75} aria-hidden="true" />
            ) : (
              <Bot size={24} strokeWidth={1.75} aria-hidden="true" />
            )}
            <span className="sr-only">
              {assistantOpen ? "Close assistant" : "Ask the assistant"}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Development panel.
 *
 * Deep Thinking reports each condition separately rather than a single
 * pass/fail: its thresholds are estimates with no published reference
 * distribution behind them, and knowing which condition blocks it is the
 * difference between measuring a threshold and guessing at it again.
 */
function Diagnostics({ diagnostics, dropped, state, confidence, deepThinking }) {
  const {
    smoothing,
    fatigue,
    furrow,
    deep_thinking: dt,
    recovery,
    rereading,
    intervention,
  } = diagnostics;

  const mono = {
    fontFamily: "monospace",
    fontSize: "0.78rem",
    color: "#777",
    textAlign: "left",
    marginTop: "0.5rem",
  };

  const flag = (ok) => ({ color: ok ? "green" : "#c00" });

  return (
    <details style={{ marginTop: "0.5rem", fontSize: "0.85rem", overflowX: "auto" }}>
      <summary style={{ cursor: "pointer", color: "#666" }}>Diagnostics</summary>
      <div style={mono}>
        {/* Scope 6.8 forbids showing this to the learner - it lives here,
            behind the collapsed disclosure above, and nowhere else. */}
        <div>
          reported state: {state} ({(confidence * 100).toFixed(1)}%)
          {deepThinking && " — reflecting"}
        </div>

        {smoothing && (
          <div>
            raw: {smoothing.raw_state} —{" "}
            {smoothing.stable
              ? "confirmed"
              : `confirming (${smoothing.streak}/${smoothing.required})`}
          </div>
        )}

        {fatigue && !fatigue.fatigue_available && (
          <div>fatigue: calibrate to enable</div>
        )}
        {fatigue && fatigue.fatigue_available && (
          <div>
            fatigue: eyes low {Math.round(fatigue.fatigue_ratio * 100)}% of 45s ·
            {fatigue.fatigue_pose_pitch != null
              ? ` solvePnP pitch ${fatigue.fatigue_pose_pitch}°`
              : ` pitch delta ${fatigue.fatigue_pitch_delta} (recalibrate for solvePnP)`}
            {fatigue.fatigue_head_down && (
              <strong style={{ color: "#0b6bcb" }}>
                {" "}
                ← looking down, window skipped
              </strong>
            )}
          </div>
        )}

        {furrow?.furrow_off_pose && (
          <div>furrow: head off-pose, reading not meaningful</div>
        )}
        {furrow?.furrow_available && (
          <div>
            furrow: inter-brow {furrow.furrow_ratio} · brow-raise{" "}
            {furrow.furrow_brow_ratio} (1.0 = baseline)
            {furrow.furrowed && (
              <strong style={{ color: "#0b6bcb" }}> ← furrowed</strong>
            )}
          </div>
        )}

        {dt?.dt_available && (
          <div>
            deep-thinking:{" "}
            <span style={flag(dt.dt_gaze_ok)}>
              gaze {dt.dt_gaze_var.toExponential(2)}
              {dt.dt_gaze_ok ? " ok" : " HIGH"}
            </span>
            {" · "}
            <span style={flag(dt.dt_ear_ok)}>
              EAR {dt.dt_ear_var.toExponential(2)}
              {dt.dt_ear_ok ? " ok" : " HIGH"}
            </span>
            {" · "}
            <span style={flag(dt.dt_pitch_ok)}>
              pitch delta {dt.dt_pitch_delta}
              {dt.dt_pitch_ok ? " ok" : " NOT DOWN"}
            </span>
            {" · "}
            <span style={flag(dt.dt_state_ok)}>
              state {dt.dt_state_ok ? "ok" : "not drifting/struggling"}
            </span>
          </div>
        )}

        {recovery && recovery.recovery_remaining > 0 && (
          <div>recovery: {recovery.recovery_remaining} more windows needed</div>
        )}

        {rereading && <div>re-reading: {rereading.status} ({rereading.reason})</div>}

        {/* "Why did nothing happen" is the question this path gets asked most,
            and the backend answers it on every window rather than only in a
            log. Development instrument, like everything else in this panel. */}
        {intervention && <div>intervention: {intervention}</div>}

        {dropped > 0 && (
          <div>
            windows skipped while a request was in flight: {dropped}
          </div>
        )}
      </div>
    </details>
  );
}

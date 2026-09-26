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

import { useMemo, useState } from "react";

import { AssistantPanel } from "../features/ai-assistant/AssistantPanel";
import { fallbackStudyContext } from "../features/ai-assistant/demoStudyContext";
import ContentViewer from "../content/ContentViewer";
import { useContent } from "../content/useContent";
import PreSessionCheck from "../engagement/PreSessionCheck";
import { useEngagementCapture } from "../engagement/useEngagementCapture";
import { useFacePresence } from "../engagement/useFacePresence";
import { usePreSessionCheck } from "../engagement/usePreSessionCheck";
import InterventionHost from "../intervention/InterventionHost";
import { useDwell } from "../intervention/useDwell";
import { useIntervention } from "../intervention/useIntervention";

/** How a reported state is labelled and coloured. */
const STATE_DISPLAY = {
  focused: { label: "Focused", color: "#137333" },
  drifting: { label: "Drifting", color: "#8a6d00" },
  struggling: { label: "Struggling", color: "#b3261e" },
  fatigued: { label: "Fatigued", color: "#c46a00" },
  recovered: { label: "Recovered", color: "#137333" },
};

function describeState(state) {
  return STATE_DISPLAY[state] ?? { label: state ?? "Unknown", color: "inherit" };
}

/**
 * High contrast follows the document, not a prop.
 *
 * It used to be passed down from `App`, which read the wrong profile key
 * (`contrast` rather than `high_contrast`), so it was permanently false. Now
 * `useAccessibility` sets `data-contrast` on <html> and this reads it, which
 * means the setting reaches this screen without anything having to remember to
 * thread it through. The prop is kept as an override for tests.
 */
function documentPrefersHighContrast() {
  if (typeof document === "undefined") return false;
  return document.documentElement.getAttribute("data-contrast") === "high";
}

export default function StudySession({ contentId, chunkId, highContrast }) {
  const [started, setStarted] = useState(false);
  const useHighContrast = highContrast ?? documentPrefersHighContrast();
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
  const dwell = useDwell({ enabled: started });

  // The chunk the learner is actually on beats whatever was passed in. The
  // prop stays as the fallback for a session with no document (the camera-only
  // path this page started as), and so the caller can pin a chunk in a test.
  const activeChunkId = dwell.chunkId ?? chunkId;

  const capture = useEngagementCapture({
    active: started,
    contentId,
    chunkId: activeChunkId,
    getDwellSeconds: dwell.seconds,
  });
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

  const panelStyle = {
    maxWidth: "520px",
    width: "90%",
    maxHeight: "85vh",
    overflowY: "auto",
    padding: "1.5rem",
    borderRadius: "8px",
    backgroundColor: useHighContrast ? "#000" : "#fff",
    color: useHighContrast ? "#fff" : "#000",
    border: `1px solid ${useHighContrast ? "#fff" : "#ccc"}`,
    boxShadow: "0 4px 20px rgba(0,0,0,0.25)",
  };

  const centeredColumn = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
    maxWidth: "760px",
    margin: "0 auto",
  };

  // Enlarging the camera view must not move the <video> element in the React
  // tree: remounting it drops srcObject and the picture goes black.
  const videoWrap = presence.faceLost
    ? {
        position: "fixed",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        zIndex: 950,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
      }
    : {
        position: "relative",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        marginBottom: "0.75rem",
      };

  return (
    <div>
      {/* Keyframes cannot be expressed as inline styles. */}
      <style>{`
        @keyframes adaptly-draw  { to { stroke-dashoffset: 0; } }
        @keyframes adaptly-pop   { from { transform: scale(.6); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        @keyframes adaptly-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .55; } }
      `}</style>

      {/* The session's own camera is not requested until this is dismissed.
          The check below opens a short-lived probe stream of its own and stops
          it again, so the two never share a stream. */}
      {!started && (
        <PreSessionCheck
          check={preSession}
          warnings={document_.content?.warnings ?? []}
          onStart={() => setStarted(true)}
          panelStyle={panelStyle}
        />
      )}

      {/* Dim everything behind the enlarged view so the instruction is
          unmissable while the learner is out of frame. */}
      {presence.faceLost && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(0,0,0,0.6)",
            zIndex: 900,
          }}
        />
      )}

      <div style={centeredColumn}>
        <div style={videoWrap}>
          <video
            ref={capture.videoRef}
            autoPlay
            playsInline
            muted
            style={{
              width: presence.faceLost ? "min(86vw, 640px)" : "min(90vw, 400px)",
              borderRadius: "12px",
              display: started ? "block" : "none",
              border: `3px solid ${presence.faceLost ? "#f5a524" : "transparent"}`,
              transition: "width .25s ease, border-color .25s ease",
              transform: "scaleX(-1)", // mirrored, so moving left feels like left
            }}
          />

          {presence.faceLost && (
            <div style={{ marginTop: "0.75rem", color: "#fff" }}>
              <p
                style={{
                  fontSize: "1.15rem",
                  margin: 0,
                  animation: "adaptly-pulse 1.4s ease-in-out infinite",
                }}
              >
                Move back into the frame
              </p>
              <p style={{ fontSize: "0.9rem", opacity: 0.8, marginTop: "0.35rem" }}>
                Centre your face in the view above
              </p>
            </div>
          )}

          {presence.showTick && (
            <div
              aria-live="polite"
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                pointerEvents: "none",
              }}
            >
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
                  stroke="#22c55e"
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
                  stroke="#22c55e"
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
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexWrap: "wrap",
              gap: "0.4rem",
              padding: "0.6rem 0.9rem",
              marginBottom: "0.75rem",
              borderRadius: "8px",
              fontSize: "0.9rem",
              border: `1px solid ${useHighContrast ? "#fff" : "#f0c36d"}`,
              backgroundColor: useHighContrast ? "#000" : "#fdf6e3",
              color: useHighContrast ? "#fff" : "#000",
            }}
          >
            <span>
              You were away for a moment. If you moved or changed seat,
              recalibrate.
            </span>
            <span style={{ whiteSpace: "nowrap" }}>
              <button
                onClick={capture.runCalibration}
                disabled={!capture.ready || capture.calibrating}
              >
                Recalibrate
              </button>
              <button
                onClick={presence.dismissRecalibrate}
                style={{ marginLeft: "0.4rem" }}
              >
                Dismiss
              </button>
            </span>
          </div>
        )}

        <p style={{ margin: "0.25rem 0" }}>{capture.status}</p>
        <p style={{ margin: "0.25rem 0" }}>
          Face detected: {capture.faceDetected ? "Yes" : "No"} · Frames:{" "}
          {capture.framesCollected} / {capture.windowSize}
        </p>
        {capture.lightingWarning && (
          <p style={{ color: "orange", margin: "0.25rem 0" }}>
            {capture.lightingWarning}
          </p>
        )}

        <div style={{ margin: "0.5rem 0" }}>
          <button
            onClick={capture.runCalibration}
            disabled={!capture.ready || capture.calibrating}
          >
            {capture.calibrating
              ? "Calibrating..."
              : capture.calibrated
              ? "Recalibrate"
              : "Calibrate now"}
          </button>
          {capture.calibrating && (
            <span style={{ marginLeft: "0.75rem" }}>
              Look naturally at the screen...
            </span>
          )}
          {capture.calibrated && !capture.calibrating && (
            <span style={{ marginLeft: "0.75rem", color: "green" }}>Calibrated</span>
          )}
        </div>
        {capture.calibrationError && (
          <p style={{ color: "red" }}>
            Calibration failed: {capture.calibrationError}
          </p>
        )}

        {/* Two waits happen before a state can appear: the window filling at
            one frame per second, and the first prediction, which loads
            TensorFlow. The backend warms the model on startup, so the second is
            usually over before anyone reaches this screen. */}
        {started && !prediction && (
          <div style={{ margin: "0.75rem 0", minHeight: "3.5rem" }}>
            <p style={{ fontSize: "1.1rem", margin: "0.25rem 0", color: "#666" }}>
              <strong>
                {capture.framesCollected < capture.windowSize
                  ? `Getting ready — ${capture.windowSize - capture.framesCollected}s`
                  : "Analysing your first reading..."}
              </strong>
            </p>
            <div
              style={{
                height: "4px",
                width: "260px",
                margin: "0.6rem auto 0",
                background: "#e0e0e0",
                borderRadius: "2px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.min(100, (capture.framesCollected / capture.windowSize) * 100)}%`,
                  background: "#0b6bcb",
                  transition: "width .4s ease",
                }}
              />
            </div>
          </div>
        )}

        {/* What the learner is here to read. Above the support, so an offer
            appears under the text it is about rather than pushing it down. */}
        {contentId && (
          <div style={{ width: "100%", maxWidth: "620px", textAlign: "left" }}>
            {document_.loading && <p>Loading the document...</p>}
            {document_.error && (
              <p style={{ color: "#b3261e" }}>{document_.error}</p>
            )}
            {document_.content && (
              <ContentViewer
                content={document_.content}
                onChunkRef={dwell.register}
              />
            )}
          </div>
        )}

        {/* Module 4's support, inline and quiet. Scope 6.4 asks for this
            "without any sound, flash, or alert", so it sits in the normal
            flow of the page rather than over it. */}
        <div style={{ width: "100%", maxWidth: "620px" }}>
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

        {prediction && (
          <>
            <p style={{ fontSize: "1.1rem", margin: "0.5rem 0" }}>
              <strong style={{ color: display.color }}>{display.label}</strong>{" "}
              <span style={{ color: "#666", fontSize: "0.85rem" }}>
                ({(prediction.confidence * 100).toFixed(1)}%)
              </span>
              {deepThinking && (
                <span style={{ color: "#0b6bcb", fontSize: "0.85rem" }}>
                  {" "}
                  — reflecting
                </span>
              )}
            </p>

            {diagnostics && (
              <Diagnostics diagnostics={diagnostics} dropped={capture.droppedWindows} />
            )}
          </>
        )}
      </div>

      {/* Module 5. Fixed-position and collapsed by default so it never moves
          or resizes anything above - the engagement/intervention layout is
          untouched either way. Only offered once a session is running,
          since studyContext.session_id only means anything at that point. */}
      {started && (
        <div style={{ position: "fixed", bottom: "1rem", right: "1rem", zIndex: 800 }}>
          <button type="button" onClick={() => setAssistantOpen((open) => !open)}>
            {assistantOpen ? "Close assistant" : "Ask the assistant"}
          </button>
          {assistantOpen && (
            <div
              style={{
                marginTop: "0.5rem",
                width: "min(90vw, 360px)",
                maxHeight: "70vh",
                overflowY: "auto",
                borderRadius: "8px",
                border: `1px solid ${useHighContrast ? "#fff" : "#ccc"}`,
                backgroundColor: useHighContrast ? "#000" : "#fff",
                color: useHighContrast ? "#fff" : "#000",
                boxShadow: "0 4px 20px rgba(0,0,0,0.25)",
              }}
            >
              <AssistantPanel studyContext={studyContext} />
            </div>
          )}
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
function Diagnostics({ diagnostics, dropped }) {
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

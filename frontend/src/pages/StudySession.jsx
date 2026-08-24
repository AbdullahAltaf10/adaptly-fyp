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

import { useState } from "react";

import { useEngagementCapture } from "../engagement/useEngagementCapture";
import { useFacePresence } from "../engagement/useFacePresence";

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

export default function StudySession({ contentId, chunkId, highContrast = false }) {
  const [started, setStarted] = useState(false);

  const capture = useEngagementCapture({ active: started, contentId, chunkId });
  const presence = useFacePresence({
    faceDetected: capture.faceDetected,
    enabled: started && capture.ready,
    calibrated: capture.calibrated,
  });

  const { prediction } = capture;
  const diagnostics = prediction?.diagnostics ?? null;
  const display = describeState(prediction?.state);
  const deepThinking = diagnostics?.deep_thinking?.deep_thinking;

  const panelStyle = {
    maxWidth: "520px",
    width: "90%",
    maxHeight: "85vh",
    overflowY: "auto",
    padding: "1.5rem",
    borderRadius: "8px",
    backgroundColor: highContrast ? "#000" : "#fff",
    color: highContrast ? "#fff" : "#000",
    border: `1px solid ${highContrast ? "#fff" : "#ccc"}`,
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

      {/* The camera is not requested until this has been dismissed. */}
      {!started && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="session-instructions-title"
          style={{
            position: "fixed",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "rgba(0,0,0,0.55)",
            zIndex: 1000,
          }}
        >
          <div style={panelStyle}>
            <h3 id="session-instructions-title" style={{ marginTop: 0 }}>
              Before you start
            </h3>
            <p style={{ marginTop: 0 }}>
              Your camera is used to measure engagement.{" "}
              <strong>No video is recorded, stored, or sent anywhere</strong> —
              only numeric facial measurements leave your browser.
            </p>
            <ol style={{ paddingLeft: "1.2rem", lineHeight: 1.7 }}>
              <li>
                Sit about an arm&apos;s length away, with your whole face
                visible and roughly centred.
              </li>
              <li>
                Make sure your face is well lit. Avoid sitting with a bright
                window directly behind you.
              </li>
              <li>
                Once the camera is active, choose <strong>Calibrate Now</strong>{" "}
                and look naturally at the screen for about three seconds.
              </li>
              <li>
                <strong>Recalibrate if a different person takes over</strong>, or
                if you move your laptop or change seat — the baseline is per
                person and per camera angle.
              </li>
            </ol>
            <button onClick={() => setStarted(true)} style={{ marginTop: "0.5rem" }}>
              Start session
            </button>
          </div>
        </div>
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
              border: `1px solid ${highContrast ? "#fff" : "#f0c36d"}`,
              backgroundColor: highContrast ? "#000" : "#fdf6e3",
              color: highContrast ? "#fff" : "#000",
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
  const { smoothing, fatigue, furrow, deep_thinking: dt, recovery, rereading } =
    diagnostics;

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

        {dropped > 0 && (
          <div>
            windows skipped while a request was in flight: {dropped}
          </div>
        )}
      </div>
    </details>
  );
}

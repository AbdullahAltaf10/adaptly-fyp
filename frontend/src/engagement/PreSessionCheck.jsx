/**
 * What the learner sees before a session starts (scope 6.2).
 *
 * Replaces a dialog that gave instructions and verified nothing. It now
 * reports the two things scope asks about — is the webcam working, is the
 * lighting adequate — plus any warnings Module 2 raised about the document
 * itself, which were being computed and discarded.
 *
 * "Start session" stays disabled while the camera is unavailable, because a
 * session without it measures nothing. It is *not* disabled for low light:
 * detection degrades rather than stops, and someone studying in a dim room at
 * night has made a reasonable choice that this screen has no business
 * overriding.
 */

import {
  CAMERA_DENIED,
  CAMERA_FAILED,
  CAMERA_MISSING,
} from "./usePreSessionCheck";
import { describeContentWarning } from "../content/warnings";

const CAMERA_PROBLEMS = {
  [CAMERA_DENIED]:
    "Camera access was blocked. Allow it in your browser's address bar, then check again.",
  [CAMERA_MISSING]:
    "No camera was found. Connect one and check again.",
  [CAMERA_FAILED]:
    "The camera could not be started. It may be in use by another application.",
};

function Row({ ok, children }) {
  const colour = ok === true ? "#137333" : ok === false ? "#b3261e" : "#8a6d00";
  const mark = ok === true ? "✓" : ok === false ? "✗" : "–";
  return (
    <li style={{ color: colour, listStyle: "none", margin: "0.3rem 0" }}>
      <span aria-hidden="true" style={{ marginRight: "0.5rem" }}>{mark}</span>
      {children}
    </li>
  );
}

/**
 * `document` is the state of the document this session is about, when it has
 * one: `{ loading, error }`, or omitted for a camera-only session.
 *
 * It gates Start for the same reason the camera does. A learner who chose a
 * document and then hits Start while it is still loading gets a session with
 * nothing to read, and one whose document failed to load gets the same with no
 * explanation - the error used to sit behind this dialog where nobody could see
 * it. Neither is the camera's fault, so it is reported separately.
 *
 * `calibrated` is `true`, `false` or `null` (unknown). It is advice and never a
 * gate: someone who has not calibrated can still study, but they are served the
 * original engagement model rather than the one tuned to their own baseline, and
 * the two differ enough to be worth a sentence. `null` says nothing at all -
 * "we could not check" must not turn into "you have not calibrated".
 */
export default function PreSessionCheck({
  check,
  warnings = [],
  document,
  calibrated = null,
  onStart,
  panelStyle,
}) {
  const problem = CAMERA_PROBLEMS[check.camera];
  const documentLoading = Boolean(document?.loading);
  const documentError = document?.error ?? null;
  const canStart = check.cameraReady && !documentLoading && !documentError;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="pre-session-title"
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
        <h3 id="pre-session-title" style={{ marginTop: 0 }}>
          Before you start
        </h3>

        <p style={{ marginTop: 0 }}>
          Your camera is used to measure engagement.{" "}
          <strong>No video is recorded, stored, or sent anywhere</strong> — only
          numeric facial measurements leave your browser.
        </p>

        {/* Off-screen: needed to read a frame for the brightness measurement,
            but there is nothing useful for the learner in a 900ms preview. */}
        <video
          ref={check.videoRef}
          muted
          playsInline
          style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
        />

        <ul aria-live="polite" style={{ padding: 0, margin: "0.75rem 0" }}>
          {check.checking ? (
            <Row ok={null}>Checking your camera...</Row>
          ) : (
            <>
              <Row ok={check.cameraReady}>
                {check.cameraReady ? "Camera is working" : "Camera is not available"}
              </Row>
              {check.cameraReady && calibrated === true && (
                <Row ok={true}>Calibrated to you - support is tuned to your own baseline</Row>
              )}
              {check.cameraReady && calibrated === false && (
                <Row ok={null}>
                  Not calibrated yet. You can start now, but support is less accurate until you
                  calibrate - there is a Calibrate button once the session begins, and it is
                  remembered for next time.
                </Row>
              )}
              {check.cameraReady && (
                <Row ok={check.lowLight === null ? null : !check.lowLight}>
                  {check.lowLight === null
                    ? "Lighting could not be measured"
                    : check.lowLight
                    ? "Lighting is low — a brighter room gives more accurate detection. You can still start."
                    : "Lighting looks fine"}
                </Row>
              )}
            </>
          )}
        </ul>

        {problem && (
          <p style={{ color: "#b3261e", margin: "0.5rem 0" }}>{problem}</p>
        )}

        {documentLoading && (
          <p role="status" style={{ margin: "0.5rem 0" }}>
            Loading your document...
          </p>
        )}

        {documentError && (
          <div role="alert" style={{ margin: "0.5rem 0", color: "#b3261e" }}>
            <p style={{ margin: "0 0 0.25rem" }}>
              This document could not be opened, so there is nothing to read in this session.
            </p>
            <a href="/library" style={{ color: "inherit", textDecoration: "underline" }}>
              Choose another document
            </a>
          </div>
        )}

        {warnings.length > 0 && (
          <div style={{ margin: "0.75rem 0" }}>
            <h4 style={{ margin: "0 0 0.35rem", fontSize: "0.95rem" }}>
              About this document
            </h4>
            <ul style={{ paddingLeft: "1.2rem", margin: 0, lineHeight: 1.6 }}>
              {warnings.map((code) => (
                <li key={code}>{describeContentWarning(code)}</li>
              ))}
            </ul>
          </div>
        )}

        <ol style={{ paddingLeft: "1.2rem", lineHeight: 1.7 }}>
          <li>
            Sit about an arm&apos;s length away, with your whole face visible and
            roughly centred.
          </li>
          <li>Keep your face lit from the front rather than from behind.</li>
        </ol>

        <div style={{ marginTop: "0.5rem" }}>
          <button onClick={onStart} disabled={!canStart}>
            Start session
          </button>
          {!check.cameraReady && !check.checking && (
            <button onClick={check.recheck} style={{ marginLeft: "0.5rem" }}>
              Check again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

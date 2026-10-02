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
  AlertTriangle,
  BookOpenText,
  Camera,
  CheckCircle2,
  CircleX,
  Lightbulb,
  Loader2,
} from "lucide-react";

import {
  CAMERA_DENIED,
  CAMERA_FAILED,
  CAMERA_MISSING,
} from "./usePreSessionCheck";
import { describeContentWarning } from "../content/warnings";
import { Button } from "../ui";

const CAMERA_PROBLEMS = {
  [CAMERA_DENIED]:
    "Camera access was blocked. Allow it in your browser's address bar, then check again.",
  [CAMERA_MISSING]:
    "No camera was found. Connect one and check again.",
  [CAMERA_FAILED]:
    "The camera could not be started. It may be in use by another application.",
};

/** One line in the checklist: a status mark, an icon for what it is about, the text. */
function Row({ ok, icon: Icon, children }) {
  const colour = ok === true ? "text-success" : ok === false ? "text-danger" : "text-muted";
  const Mark = ok === true ? CheckCircle2 : ok === false ? CircleX : Loader2;

  return (
    <li className={`flex items-start gap-2 ${colour}`}>
      <Mark
        size={16}
        strokeWidth={1.75}
        className={`shrink-0 mt-0.5 ${ok === null ? "animate-spin" : ""}`}
        aria-hidden="true"
      />
      <Icon size={16} strokeWidth={1.75} className="shrink-0 mt-0.5 text-muted" aria-hidden="true" />
      <span className="text-ink">{children}</span>
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
 */
export default function PreSessionCheck({ check, warnings = [], document, onStart }) {
  const problem = CAMERA_PROBLEMS[check.camera];
  const documentLoading = Boolean(document?.loading);
  const documentError = document?.error ?? null;
  const canStart = check.cameraReady && !documentLoading && !documentError;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="pre-session-title"
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/55 p-4"
    >
      <div className="w-full max-w-[480px] max-h-[85vh] overflow-y-auto rounded-card shadow-floating border border-line bg-surface text-ink p-6">
        <h3 id="pre-session-title" className="m-0 mb-3 text-lg font-semibold">
          Before you start
        </h3>

        <p className="mt-0 mb-3 text-sm text-muted">
          Your camera is used to measure engagement.{" "}
          <strong className="text-ink">No video is recorded, stored, or sent anywhere</strong> —
          only numeric facial measurements leave your browser.
        </p>

        {/* Off-screen: needed to read a frame for the brightness measurement,
            but there is nothing useful for the learner in a 900ms preview. */}
        <video
          ref={check.videoRef}
          muted
          playsInline
          style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
        />

        <ul aria-live="polite" className="p-0 m-0 mb-3 space-y-1.5 list-none">
          {check.checking ? (
            <Row ok={null} icon={Camera}>
              Checking your camera...
            </Row>
          ) : (
            <>
              <Row ok={check.cameraReady} icon={Camera}>
                {check.cameraReady ? "Camera is working" : "Camera is not available"}
              </Row>
              {check.cameraReady && (
                <Row ok={check.lowLight === null ? null : !check.lowLight} icon={Lightbulb}>
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

        {check.cameraReady && check.webgazerStatus !== "unavailable" && (
          <div className="rounded-md border border-line bg-page p-3 mb-3">
            <p className="m-0 mb-2 text-sm text-ink">
              Optional: calibrate eye tracking for better paragraph focus.
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                onClick={check.startWebgazerCalibration}
                disabled={check.webgazerStatus === "calibrating" || check.webgazerStatus === "ready"}
              >
                {check.webgazerStatus === "ready" ? "Calibrated" : "Calibrate"}
              </Button>
              <Button variant="secondary" onClick={check.skipWebgazerCalibration}>
                Skip
              </Button>
            </div>
          </div>
        )}

        {check.readabilitySuggestion && (
          <div
            role="status"
            className="flex items-start justify-between gap-2 rounded-md border border-line bg-page p-3 mb-3 text-sm"
          >
            <span>Larger text might make this easier to follow.</span>
            <Button variant="secondary" onClick={check.dismissReadabilitySuggestion}>
              Dismiss
            </Button>
          </div>
        )}

        {problem && (
          <p className="flex items-start gap-2 text-danger text-sm mb-3">
            <AlertTriangle size={16} strokeWidth={1.75} className="shrink-0 mt-0.5" aria-hidden="true" />
            {problem}
          </p>
        )}

        {documentLoading && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted mb-3">
            <Loader2 size={14} strokeWidth={1.75} className="animate-spin shrink-0" aria-hidden="true" />
            Loading your document...
          </p>
        )}

        {documentError && (
          <div role="alert" className="rounded-md border-l-4 border-l-danger bg-danger-soft text-ink text-sm p-3 mb-3">
            <p className="m-0 mb-1">
              This document could not be opened, so there is nothing to read in this session.
            </p>
            <a href="/library" className="text-accent hover:underline">
              Choose another document
            </a>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="rounded-md border border-line bg-page p-3 mb-3">
            <h4 className="flex items-center gap-1.5 m-0 mb-2 text-sm font-semibold">
              <BookOpenText size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
              About this document
            </h4>
            <ul className="pl-5 m-0 space-y-1 text-sm text-ink">
              {warnings.map((code) => (
                <li key={code}>{describeContentWarning(code)}</li>
              ))}
            </ul>
          </div>
        )}

        <ol className="pl-5 m-0 mb-4 space-y-1 text-sm text-ink leading-relaxed">
          <li>
            Sit about an arm&apos;s length away, with your whole face visible and roughly
            centred.
          </li>
          <li>Keep your face lit from the front rather than from behind.</li>
        </ol>

        <div className="flex items-center gap-2">
          <Button onClick={onStart} disabled={!canStart}>
            Start session
          </Button>
          {!check.cameraReady && !check.checking && (
            <Button variant="secondary" onClick={check.recheck}>
              Check again
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

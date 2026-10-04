/**
 * The pre-session check scope section 6.2 asks for: confirm the webcam is
 * working and the lighting is adequate, before the session begins.
 *
 * Both were already half-present and neither was a check. The "Before you
 * start" dialog gave instructions without verifying anything, and lighting was
 * only measured once the session was already running — by which point a
 * learner in a dark room has started a session that cannot measure them.
 *
 * Two outcomes, deliberately weighted differently:
 *
 * **No camera is a hard stop.** Without it there is no engagement detection at
 * all, and starting anyway would produce a session that silently measures
 * nothing. The learner is told which failure it was, because "permission
 * denied" and "no camera attached" need different things done about them.
 *
 * **Low light is a warning, not a block.** Detection degrades rather than
 * stops, and someone studying at night in a dim room is making a reasonable
 * choice. Telling them the measurements will be less reliable respects that;
 * refusing to let them study does not.
 *
 * The probe stream is opened, measured, and stopped here. It is never handed
 * to the capture loop, which opens its own — sharing one would mean this
 * file's lifetime controlled the session's camera.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { averageBrightness, isLowLight } from "./landmarks";
import { CALIBRATION_POINTS, calibrateWebgazer, stopWebgazer } from "./webgazerSignal";

/** Enough frames for auto-exposure to settle; a first frame reads far too dark. */
const SETTLE_MS = 900;

/** How many fusionConfidence samples the readability probe collects before judging. */
const READABILITY_PROBE_SECONDS = 8;
/** Below this average confidence, the signals never settled on a clear target. */
const SCATTERED_CONFIDENCE_THRESHOLD = 0.3;

export const CAMERA_UNKNOWN = "unknown";
export const CAMERA_OK = "ok";
export const CAMERA_DENIED = "denied";
export const CAMERA_MISSING = "missing";
export const CAMERA_FAILED = "failed";

function classifyCameraError(error) {
  const name = error?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return CAMERA_DENIED;
  if (name === "NotFoundError" || name === "DevicesNotFoundError") return CAMERA_MISSING;
  return CAMERA_FAILED;
}

export function usePreSessionCheck({ enabled = true } = {}) {
  const [camera, setCamera] = useState(CAMERA_UNKNOWN);
  const [brightness, setBrightness] = useState(null);
  const [checking, setChecking] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const videoRef = useRef(null);

  const [webgazerStatus, setWebgazerStatus] = useState("idle");
  const [calibrationPointsClicked, setCalibrationPointsClicked] = useState(() => new Set());
  const [readabilitySuggestion, setReadabilitySuggestion] = useState(null);
  const confidenceSamplesRef = useRef([]);

  const recheck = useCallback(() => setAttempt((n) => n + 1), []);

  const startWebgazerCalibration = useCallback(async () => {
    setWebgazerStatus("calibrating");
    const result = await calibrateWebgazer();
    // "available" only means WebGazer's camera/regression started, not that
    // it has learned anything yet - see webgazerSignal.js's own docstring.
    // A real click at each of CALIBRATION_POINTS is what actually trains it,
    // via addMouseEventListeners(); only once all of them have fired is the
    // gaze estimate worth anything.
    setCalibrationPointsClicked(new Set());
    setWebgazerStatus(result.available ? "awaiting-points" : "unavailable");
  }, []);

  const recordCalibrationPoint = useCallback((index) => {
    setCalibrationPointsClicked((current) => {
      if (current.has(index)) return current;
      const next = new Set(current);
      next.add(index);
      if (next.size >= CALIBRATION_POINTS.length) {
        setWebgazerStatus("ready");
      }
      return next;
    });
  }, []);

  const skipWebgazerCalibration = useCallback(() => {
    setWebgazerStatus("unavailable");
  }, []);

  /**
   * Called by the study page once per fusion tick during the readability
   * probe window, with the current fusionConfidence. After
   * READABILITY_PROBE_SECONDS samples, a low average suggests a suggestion.
   */
  const recordReadabilitySample = useCallback((confidence) => {
    confidenceSamplesRef.current.push(confidence);
    if (confidenceSamplesRef.current.length < READABILITY_PROBE_SECONDS) return;
    const average =
      confidenceSamplesRef.current.reduce((a, b) => a + b, 0) / confidenceSamplesRef.current.length;
    if (average < SCATTERED_CONFIDENCE_THRESHOLD) {
      setReadabilitySuggestion({ fontUp: true, lineSpacingUp: true });
    }
    confidenceSamplesRef.current = [];
  }, []);

  const dismissReadabilitySuggestion = useCallback(() => setReadabilitySuggestion(null), []);

  useEffect(() => () => stopWebgazer(), []);

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;
    let stream = null;
    let timer = null;

    const stop = () => {
      if (timer) clearTimeout(timer);
      if (stream) stream.getTracks().forEach((track) => track.stop());
      stream = null;
    };

    async function probe() {
      setChecking(true);
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (cancelled) return stop();

        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          try {
            await video.play();
          } catch {
            // Autoplay can be refused while the element is still mounting.
            // The brightness read below simply returns null in that case,
            // which is reported as "not measured" rather than as darkness.
          }
        }

        timer = setTimeout(() => {
          if (cancelled) return;
          setBrightness(video ? averageBrightness(video) : null);
          setCamera(CAMERA_OK);
          setChecking(false);
          stop();
        }, SETTLE_MS);
      } catch (error) {
        if (cancelled) return;
        setCamera(classifyCameraError(error));
        setBrightness(null);
        setChecking(false);
        stop();
      }
    }

    probe();
    return () => {
      cancelled = true;
      stop();
    };
  }, [enabled, attempt]);

  return {
    videoRef,
    checking,
    camera,
    cameraReady: camera === CAMERA_OK,
    brightness,
    // `null` means not measured, which is not the same as adequate. It is
    // reported as its own state rather than collapsed into either.
    lowLight: brightness === null ? null : isLowLight(brightness),
    recheck,
    webgazerStatus,
    startWebgazerCalibration,
    skipWebgazerCalibration,
    calibrationPointsClicked,
    recordCalibrationPoint,
    readabilitySuggestion,
    recordReadabilitySample,
    dismissReadabilitySuggestion,
  };
}

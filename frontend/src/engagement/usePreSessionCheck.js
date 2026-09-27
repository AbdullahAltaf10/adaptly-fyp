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

/** Enough frames for auto-exposure to settle; a first frame reads far too dark. */
const SETTLE_MS = 900;

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

  const recheck = useCallback(() => setAttempt((n) => n + 1), []);

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
  };
}

/**
 * The Module 3 capture loop as a React hook.
 *
 * Owns the camera, the MediaPipe landmarker, the rolling window and the calls
 * to the backend, so the study page is left with rendering only.
 *
 * Everything that can outlive a render (the video stream, the animation frame,
 * the capture interval, the landmarker) is torn down in the effect cleanup.
 * React StrictMode runs effects twice in development, and without that cleanup
 * two capture loops ran at once: frames arrived at roughly double the rate the
 * model expects, which quietly changes what a "10 second window" means.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "../api/client";
import { auth } from "../auth/firebase";
import {
  CALIBRATION_FRAMES,
  CALIBRATION_INTERVAL_MS,
  CAPTURE_INTERVAL_MS,
  MIN_VALID_FRAMES,
  WINDOW_SIZE,
} from "./constants";
import { analyze, calibrate, endSession, fetchCalibrationStatus, startSession } from "./api";
import { closeFaceLandmarker, createFaceLandmarker } from "./faceLandmarker";
import {
  averageBrightness,
  countValidFrames,
  hasFace,
  isLowLight,
  toLandmarkArray,
} from "./landmarks";

function newSessionId() {
  return (
    crypto.randomUUID?.() ??
    `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

export function useEngagementCapture({
  active,
  contentId,
  /** Fallback chunk, used only when `getChunkId` has nothing to report. */
  chunkId,
  /**
   * Returns seconds on the current chunk. A function rather than a value so
   * dwell can change every second without re-running the capture effect -
   * restarting it would tear down the camera and the landmarker.
   */
  getDwellSeconds,
  /**
   * Returns the chunk being read right now, read at send time. Same reason as
   * above: the active chunk changes as the learner scrolls, and a value in
   * this effect's dependencies would restart the camera on every scroll.
   * Passing the getter is what lets each window carry the chunk it was
   * actually captured on, which everything downstream depends on - the
   * intervention's passage lookup, the critical-section flag, and Module 8's
   * per-chunk analytics.
   */
  getChunkId,
} = {}) {
  const videoRef = useRef(null);
  const landmarkerRef = useRef(null);
  const windowRef = useRef([]);
  const sessionIdRef = useRef(null);
  const latestLandmarksRef = useRef(null);

  /**
   * True while an /analyze request is outstanding.
   *
   * Windows are produced once a second, but a request can take longer than
   * that under load. Sending the next one anyway lets two windows reach the
   * rule detectors out of order, and the rules assume windows arrive in
   * sequence. Skipping is the right response rather than queueing: a window
   * already stale by the time it would be sent has nothing useful to add.
   */
  const inFlightRef = useRef(false);
  const calibrateRef = useRef(null);

  // Kept in a ref so a new function identity on each render does not restart
  // the capture loop.
  const dwellRef = useRef(getDwellSeconds);
  dwellRef.current = getDwellSeconds;
  const chunkGetterRef = useRef(getChunkId);
  chunkGetterRef.current = getChunkId;
  const chunkFallbackRef = useRef(chunkId);
  chunkFallbackRef.current = chunkId;

  const [status, setStatus] = useState("Waiting to start...");
  const [ready, setReady] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [framesCollected, setFramesCollected] = useState(0);
  const [prediction, setPrediction] = useState(null);
  const [lightingWarning, setLightingWarning] = useState(null);
  const [calibrating, setCalibrating] = useState(false);
  const [calibrated, setCalibrated] = useState(false);
  const [calibrationError, setCalibrationError] = useState(null);
  const [droppedWindows, setDroppedWindows] = useState(0);

  if (sessionIdRef.current === null) {
    sessionIdRef.current = newSessionId();
  }

  useEffect(() => {
    if (!active) return undefined;

    // The effect body is async, so it can be torn down while still in flight.
    // Every await below re-checks `cancelled` before touching shared state.
    let cancelled = false;
    let stream = null;
    let rafId = null;
    let captureTimer = null;
    let lightingTimer = null;
    const sessionId = sessionIdRef.current;

    function detectLoop() {
      if (cancelled) return;
      const video = videoRef.current;
      const landmarker = landmarkerRef.current;
      if (video && landmarker && video.readyState >= 2) {
        setFaceDetected(
          hasFace(landmarker.detectForVideo(video, performance.now()))
        );
      }
      rafId = requestAnimationFrame(detectLoop);
    }

    function checkLighting() {
      if (cancelled) return;
      const brightness = averageBrightness(videoRef.current);
      setLightingWarning(
        isLowLight(brightness)
          ? "Lighting seems low. A brighter room gives more accurate detection."
          : null
      );
    }

    async function sendWindow(frames) {
      if (inFlightRef.current) {
        setDroppedWindows((n) => n + 1);
        return;
      }
      inFlightRef.current = true;
      try {
        // Read at send time: calibration replaces the session id, and a
        // window sent with the id captured at effect start was recorded
        // against a session that had already ended - so the session that
        // analytics shows had no engagement events at all.
        const res = await analyze(frames, {
          sessionId: sessionIdRef.current,
          contentId,
          chunkId: chunkGetterRef.current?.() ?? chunkFallbackRef.current ?? null,
          dwellSeconds: dwellRef.current?.() ?? 0,
        });
        if (!cancelled) setPrediction(res.data);
      } catch (err) {
        if (!cancelled) setStatus(`Prediction failed: ${err.message}`);
      } finally {
        inFlightRef.current = false;
      }
    }

    function captureFrame() {
      if (cancelled || !videoRef.current || !landmarkerRef.current) return;

      const results = landmarkerRef.current.detectForVideo(
        videoRef.current,
        performance.now()
      );
      const landmarks = toLandmarkArray(results);
      latestLandmarksRef.current = landmarks;
      windowRef.current.push(landmarks);
      if (windowRef.current.length > WINDOW_SIZE) windowRef.current.shift();
      setFramesCollected(windowRef.current.length);

      if (windowRef.current.length < WINDOW_SIZE) return;

      if (countValidFrames(windowRef.current) >= MIN_VALID_FRAMES) {
        sendWindow([...windowRef.current]);
      } else {
        // Mostly empty window: show nothing rather than a confident guess.
        setPrediction(null);
      }
    }

    async function runCalibration() {
      if (!landmarkerRef.current || !videoRef.current) return;
      setCalibrating(true);
      setCalibrationError(null);
      try {
        const frames = [];
        for (let i = 0; i < CALIBRATION_FRAMES; i += 1) {
          await new Promise((resolve) =>
            setTimeout(resolve, CALIBRATION_INTERVAL_MS)
          );
          if (cancelled || !landmarkerRef.current) return;
          frames.push(
            toLandmarkArray(
              landmarkerRef.current.detectForVideo(
                videoRef.current,
                performance.now()
              )
            )
          );
        }

        await calibrate(frames);
        if (cancelled) return;

        // Predictions made against the old baseline are not comparable to the
        // new ones, so start a fresh session rather than letting confirmed
        // state carry across the change.
        await endSession(sessionId).catch(() => {});
        sessionIdRef.current = newSessionId();
        await startSession(sessionIdRef.current, contentId).catch(() => {});

        windowRef.current = [];
        setFramesCollected(0);
        setPrediction(null);
        setCalibrated(true);
      } catch (err) {
        if (!cancelled) {
          setCalibrationError(
            err?.response?.data?.detail || err.message || "Calibration failed"
          );
        }
      } finally {
        if (!cancelled) setCalibrating(false);
      }
    }

    async function setup() {
      try {
        setStatus("Requesting camera access...");
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          setStatus("Camera active");
        }

        // Give the camera a moment to settle before judging the light.
        lightingTimer = setTimeout(checkLighting, 1000);

        const landmarker = await createFaceLandmarker();
        if (cancelled) {
          closeFaceLandmarker(landmarker);
          return;
        }
        landmarkerRef.current = landmarker;
        calibrateRef.current = runCalibration;

        // The backend also creates a session lazily on the first /analyze, so
        // a failure here costs the explicit reset and nothing else.
        await startSession(sessionId, contentId).catch(() => {});
        if (cancelled) return;

        // Silently calibrate a never-calibrated learner on their own first
        // few seconds, rather than requiring them to find and click
        // "Calibrate now" themselves - 2026-09-30 audit: the pre-session
        // dialog's own "Calibrate" button only calibrates WebGazer (Module
        // 4's paragraph-focus signal), not this. Without this, /calibrate's
        // own docstring already says "attentive users are classified as
        // distracted". Skipped for an already-calibrated returning learner
        // so their session id is not churned (runCalibration always starts
        // a fresh session) on every single visit. Best-effort: a failed
        // status check just proceeds uncalibrated rather than blocking
        // the session on it.
        try {
          const status = await fetchCalibrationStatus();
          if (!cancelled && !status.data.calibrated) {
            await runCalibration();
          }
        } catch {
          // Proceed uncalibrated - see comment above.
        }
        if (cancelled) return;

        setReady(true);
        detectLoop();
        captureTimer = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
      } catch (err) {
        if (!cancelled) setStatus(`Setup error: ${err.message}`);
      }
    }

    // Closing the tab or browser skips React's own unmount entirely, so the
    // cleanup below never runs and the session is left open forever - which
    // is exactly the gap behind "my session never showed up in analytics".
    // `pagehide` fires in both cases (unlike `beforeunload`, it also covers a
    // back/forward-cache navigation), and `fetch(..., { keepalive: true })`
    // is the one request shape a browser still finishes sending after the
    // page has gone. It is fire-and-forget on purpose: nothing can read a
    // response once the page that would show it is already closing.
    const endSessionOnUnload = () => {
      auth.currentUser
        ?.getIdToken()
        .then((token) => {
          fetch(`${API_BASE_URL}/engagement/session/end`, {
            method: "POST",
            keepalive: true,
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ session_id: sessionIdRef.current }),
          });
        })
        .catch(() => {});
    };
    window.addEventListener("pagehide", endSessionOnUnload);

    setup();

    return () => {
      cancelled = true;
      window.removeEventListener("pagehide", endSessionOnUnload);
      if (captureTimer) clearInterval(captureTimer);
      if (lightingTimer) clearTimeout(lightingTimer);
      if (rafId) cancelAnimationFrame(rafId);
      if (stream) stream.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
      closeFaceLandmarker(landmarkerRef.current);
      landmarkerRef.current = null;
      calibrateRef.current = null;
      windowRef.current = [];
      inFlightRef.current = false;
      setReady(false);
      setFramesCollected(0);

      // Covers every other way this effect stops: `active` turning false (the
      // learner clicked "End session" - see `endSessionNow` below, called
      // first and awaited there) and an ordinary React unmount (navigating
      // elsewhere in the app). Idempotent on the backend, so overlapping with
      // an explicit call above costs nothing.
      endSession(sessionIdRef.current).catch(() => {});
    };
  }, [active, contentId]);

  const runCalibration = useCallback(() => calibrateRef.current?.(), []);

  // Imperative, awaitable end - what "End session" actually calls, so the
  // page can wait for the backend to acknowledge (and therefore finalize)
  // before it navigates the learner to their analytics. The unmount/pagehide
  // paths above still exist as the safety net for every way a session can end
  // without a deliberate click.
  const endSessionNow = useCallback(
    () => endSession(sessionIdRef.current),
    []
  );

  return {
    videoRef,
    sessionId: sessionIdRef.current,
    status,
    ready,
    faceDetected,
    framesCollected,
    prediction,
    lightingWarning,
    calibrating,
    calibrated,
    calibrationError,
    droppedWindows,
    runCalibration,
    endSessionNow,
    windowSize: WINDOW_SIZE,
    getLatestLandmarks: () => latestLandmarksRef.current,
  };
}

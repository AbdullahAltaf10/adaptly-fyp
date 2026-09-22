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

import {
  CALIBRATION_FRAMES,
  CALIBRATION_INTERVAL_MS,
  CAPTURE_INTERVAL_MS,
  MIN_VALID_FRAMES,
  WINDOW_SIZE,
} from "./constants";
import { analyze, calibrate, endSession, startSession } from "./api";
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

export function useEngagementCapture({ active, contentId, chunkId } = {}) {
  const videoRef = useRef(null);
  const landmarkerRef = useRef(null);
  const windowRef = useRef([]);
  const sessionIdRef = useRef(null);

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
        const res = await analyze(frames, { sessionId, contentId, chunkId });
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
      windowRef.current.push(toLandmarkArray(results));
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
        await startSession(sessionIdRef.current).catch(() => {});

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
        await startSession(sessionId).catch(() => {});
        if (cancelled) return;

        setReady(true);
        detectLoop();
        captureTimer = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
      } catch (err) {
        if (!cancelled) setStatus(`Setup error: ${err.message}`);
      }
    }

    setup();

    return () => {
      cancelled = true;
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

      // Best effort: the tab may be closing. The backend also expires idle
      // sessions, so a missed call here does not leak state indefinitely.
      endSession(sessionId).catch(() => {});
    };
  }, [active, contentId, chunkId]);

  const runCalibration = useCallback(() => calibrateRef.current?.(), []);

  return {
    videoRef,
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
    windowSize: WINDOW_SIZE,
  };
}

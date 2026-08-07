import { useRef, useEffect, useState } from "react";
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";

function newSessionId() {
  return crypto.randomUUID?.() ?? `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function StudySession() {
  const { profile } = useAuth();
  const videoRef = useRef(null);
  const landmarkerRef = useRef(null);
  const frameBufferRef = useRef([]);
  const sessionIdRef = useRef(null);
  const calibrateRef = useRef(null);

  const [sessionStarted, setSessionStarted] = useState(false);
  const [cameraStatus, setCameraStatus] = useState("Waiting to start...");
  const [faceDetected, setFaceDetected] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [framesCollected, setFramesCollected] = useState(0);
  const [lightingWarning, setLightingWarning] = useState(null);
  const [ready, setReady] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [calibrated, setCalibrated] = useState(false);
  const [calibrationError, setCalibrationError] = useState(null);

  // Out-of-frame handling
  const faceLostRef = useRef(false);
  const faceLostAtRef = useRef(null);
  const [faceLost, setFaceLost] = useState(false);
  const [showTick, setShowTick] = useState(false);
  const [suggestRecalibrate, setSuggestRecalibrate] = useState(false);

  // One id per session, used by the backend to key its smoothing state.
  // Must be a ref so it survives re-renders and the StrictMode remount.
  if (sessionIdRef.current === null) {
    sessionIdRef.current = newSessionId();
  }

  const highContrast = profile?.accessibility_settings?.contrast === "high";

  // Face-lost / face-found transitions.
  // Debounced by FACE_LOST_GRACE_MS because MediaPipe drops the occasional
  // frame even when the user hasn't moved — warning on every dropped frame
  // would make the overlay flicker constantly.
  const FACE_LOST_GRACE_MS = 1500;
  const RECALIBRATE_SUGGEST_MS = 5000; // away this long => they may have moved

  useEffect(() => {
    if (!sessionStarted || !ready) return;
    let timer;

    if (!faceDetected) {
      timer = setTimeout(() => {
        faceLostRef.current = true;
        faceLostAtRef.current = Date.now();
        setFaceLost(true);
      }, FACE_LOST_GRACE_MS);
    } else if (faceLostRef.current) {
      const awayMs = Date.now() - (faceLostAtRef.current ?? Date.now());
      faceLostRef.current = false;
      faceLostAtRef.current = null;
      setFaceLost(false);
      setShowTick(true);

      // A long absence often means they got up or shifted seat, which makes the
      // calibrated baseline stale (a known limitation — see PROJECT_CONTEXT
      // section 4). Offer a recalibration rather than silently re-running one:
      // an automatic baseline can quietly absorb genuine disengagement.
      if (awayMs >= RECALIBRATE_SUGGEST_MS && calibrated) {
        setSuggestRecalibrate(true);
      }
      // must outlast the draw animation (circle .9s + check .6s at .8s delay)
      timer = setTimeout(() => setShowTick(false), 2600);
    }

    return () => clearTimeout(timer);
  }, [faceDetected, sessionStarted, ready, calibrated]);

  useEffect(() => {
    // Camera does not start until the user dismisses the instructions modal.
    if (!sessionStarted) return;

    // Guards against the StrictMode double-invoke: setup() is async, so the
    // effect can be torn down while it is still in flight. Without these, the
    // first run's interval/rAF/stream keep running alongside the second run's.
    let cancelled = false;
    let stream = null;
    let rafId = null;
    let captureTimer = null;
    let lightingTimer = null;

    async function setup() {
      try {
        setCameraStatus("Requesting camera access...");
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          setCameraStatus("Camera active");
        }

        lightingTimer = setTimeout(checkLighting, 1000); // give camera a moment to stabilize

        const filesetResolver = await FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
        );
        if (cancelled) return;

        const landmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
          baseOptions: {
            modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            delegate: "GPU",
          },
          runningMode: "VIDEO",
          numFaces: 1,
        });
        // don't let a cancelled run clobber the live landmarker
        if (cancelled) {
          try { landmarker.close?.(); } catch { /* ignore */ }
          return;
        }
        landmarkerRef.current = landmarker;

        calibrateRef.current = calibrate;
        setReady(true);

        detectLoop();
        captureTimer = setInterval(captureFrame, 1000);
      } catch (err) {
        if (!cancelled) setCameraStatus("Setup error: " + err.message);
      }
    }

    function detectLoop() {
      if (cancelled) return;
      if (videoRef.current && landmarkerRef.current && videoRef.current.readyState >= 2) {
        const results = landmarkerRef.current.detectForVideo(videoRef.current, performance.now());
        setFaceDetected(results.faceLandmarks && results.faceLandmarks.length > 0);
      }
      rafId = requestAnimationFrame(detectLoop);
    }

    function checkLighting() {
      if (cancelled || !videoRef.current) return;
      const canvas = document.createElement("canvas");
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(videoRef.current, 0, 0);
      const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);

      let total = 0;
      for (let i = 0; i < frame.data.length; i += 4) {
        total += (frame.data[i] + frame.data[i + 1] + frame.data[i + 2]) / 3;
      }
      const avgBrightness = total / (frame.data.length / 4);

      if (avgBrightness < 60) {
        setLightingWarning("Lighting seems low — consider a brighter room for accurate detection.");
      } else {
        setLightingWarning(null);
      }
    }

    function captureFrame() {
      if (cancelled || !videoRef.current || !landmarkerRef.current) return;
      const results = landmarkerRef.current.detectForVideo(videoRef.current, performance.now());

      let landmarkArray = null;
      if (results.faceLandmarks && results.faceLandmarks.length > 0) {
        landmarkArray = results.faceLandmarks[0].map((p) => [p.x, p.y, p.z]);
      }

      frameBufferRef.current.push(landmarkArray);
      if (frameBufferRef.current.length > 10) {
        frameBufferRef.current.shift();
      }
      setFramesCollected(frameBufferRef.current.length);

      if (frameBufferRef.current.length === 10) {
        const validFrames = frameBufferRef.current.filter((f) => f !== null).length;
        if (validFrames >= 7) {
          sendToBackend([...frameBufferRef.current]);
        } else {
          setPrediction(null);
        }
      }
    }

    async function sendToBackend(landmarkFrames) {
      try {
        const payload = {
          frames: landmarkFrames.map((landmarks) => ({ landmarks })),
          session_id: sessionIdRef.current,
        };
        const res = await api.post("/engagement/analyze", payload);
        if (!cancelled) setPrediction(res.data);
      } catch (err) {
        console.error("Prediction error:", err);
      }
    }

    async function calibrate() {
      if (!landmarkerRef.current || !videoRef.current) return;
      setCalibrating(true);
      setCalibrationError(null);
      try {
        const framesForCalibration = [];
        for (let i = 0; i < 10; i++) {
          await new Promise((resolve) => setTimeout(resolve, 300));
          if (cancelled || !landmarkerRef.current) return;
          const results = landmarkerRef.current.detectForVideo(videoRef.current, performance.now());
          const landmarks =
            results.faceLandmarks && results.faceLandmarks.length > 0
              ? results.faceLandmarks[0].map((p) => [p.x, p.y, p.z])
              : null;
          framesForCalibration.push({ landmarks });
        }

        const res = await api.post("/engagement/calibrate", { frames: framesForCalibration });
        console.log("Calibration result:", res.data);

        if (!cancelled) {
          // Predictions made under the previous offset aren't comparable to the
          // new ones, so start a fresh smoothing session rather than letting
          // stale confirmed state carry over.
          sessionIdRef.current = newSessionId();
          setPrediction(null);
          setCalibrated(true);
          setSuggestRecalibrate(false);
        }
      } catch (err) {
        if (!cancelled) {
          setCalibrationError(err?.response?.data?.detail || err.message || "Calibration failed");
        }
      } finally {
        if (!cancelled) setCalibrating(false);
      }
    }

    setup();

    return () => {
      cancelled = true;
      if (captureTimer) clearInterval(captureTimer);
      if (lightingTimer) clearTimeout(lightingTimer);
      if (rafId) cancelAnimationFrame(rafId);
      if (stream) stream.getTracks().forEach((t) => t.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
      if (landmarkerRef.current) {
        try { landmarkerRef.current.close?.(); } catch { /* ignore */ }
        landmarkerRef.current = null;
      }
      calibrateRef.current = null;
      frameBufferRef.current = [];
      setReady(false);
    };
  }, [sessionStarted]);

  // Fatigued outranks Recovered: a tired learner who briefly refocuses still
  // needs a break, and "Recovered" there would prompt the wrong intervention.
  const headlineState = !prediction
    ? null
    : prediction.fatigued
    ? "Fatigued"
    : prediction.deep_thinking
    ? "Deep Thinking"
    : prediction.recovered
    ? "Recovered"
    : prediction.state;

  const headlineColor =
    headlineState === "Fatigued"
      ? "#c46a00"
      : headlineState === "Deep Thinking"
      ? "#0b6bcb"
      : headlineState === "Recovered"
      ? "green"
      : "inherit";

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

  const normalVideoWrap = {
    position: "relative",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    marginBottom: "0.75rem",
  };

  // Lifts the camera view above the dimming backdrop without moving the <video>
  // element in the React tree.
  const floatingVideoWrap = {
    position: "fixed",
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)",
    zIndex: 950,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
  };

  const tickOverlay = {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    pointerEvents: "none",
  };

  const recalibratePromptStyle = {
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
  };

  const diagnosticsStyle = {
    marginTop: "0.5rem",
    fontSize: "0.85rem",
    maxWidth: "100%",
    overflowX: "auto",
  };

  return (
    <DashboardLayout title="Study Session">
      {/* Keyframes must live in a stylesheet — inline styles cannot express them. */}
      <style>{`
        @keyframes adaptly-draw  { to { stroke-dashoffset: 0; } }
        @keyframes adaptly-pop   { from { transform: scale(.6); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        @keyframes adaptly-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .55; } }
      `}</style>

      {!sessionStarted && (
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
              Your camera is used to measure engagement. <strong>No video is recorded,
              stored, or sent anywhere</strong> — only numeric facial measurements leave
              your browser.
            </p>
            <ol style={{ paddingLeft: "1.2rem", lineHeight: 1.7 }}>
              <li>Sit about an arm's length away, with your whole face visible and roughly centred.</li>
              <li>Make sure your face is well lit. Avoid sitting with a bright window directly behind you.</li>
              <li>
                Once the camera is active, click <strong>Calibrate Now</strong> and look
                naturally at the screen for about 3 seconds.
              </li>
              <li>
                <strong>Recalibrate if a different person takes over</strong>, or if you move
                your laptop or change seat — the baseline is per person and per camera angle.
              </li>
            </ol>
            <button onClick={() => setSessionStarted(true)} style={{ marginTop: "0.5rem" }}>
              Start Session
            </button>
          </div>
        </div>
      )}

      {/* Dim everything behind the enlarged camera view while the face is out
          of frame, so the instruction is unmissable. */}
      {faceLost && (
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
        {/* The video stays in this exact position in the tree whether or not it
            is enlarged — moving it would remount the element and drop srcObject. */}
        <div style={faceLost ? floatingVideoWrap : normalVideoWrap}>
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            style={{
              width: faceLost ? "min(86vw, 640px)" : "min(90vw, 400px)",
              borderRadius: "12px",
              display: sessionStarted ? "block" : "none",
              border: faceLost ? "3px solid #f5a524" : "3px solid transparent",
              transition: "width .25s ease, border-color .25s ease",
              transform: "scaleX(-1)", // mirror, so moving left feels like left
            }}
          />

          {faceLost && (
            <div style={{ marginTop: "0.75rem", color: "#fff", textAlign: "center" }}>
              <p style={{ fontSize: "1.15rem", margin: 0, animation: "adaptly-pulse 1.4s ease-in-out infinite" }}>
                Move back into the frame
              </p>
              <p style={{ fontSize: "0.9rem", opacity: 0.8, marginTop: "0.35rem" }}>
                Centre your face in the view above
              </p>
            </div>
          )}

          {showTick && (
            <div style={tickOverlay} aria-live="polite">
              <svg viewBox="0 0 52 52" width="110" height="110" style={{ animation: "adaptly-pop .5s ease-out both" }}>
                <circle
                  cx="26" cy="26" r="24" fill="none" stroke="#22c55e" strokeWidth="3"
                  style={{ strokeDasharray: 151, strokeDashoffset: 151, animation: "adaptly-draw .9s ease-out forwards" }}
                />
                <path
                  d="M14 27 l8 8 l16 -16" fill="none" stroke="#22c55e" strokeWidth="4"
                  strokeLinecap="round" strokeLinejoin="round"
                  style={{ strokeDasharray: 48, strokeDashoffset: 48, animation: "adaptly-draw .6s .8s ease-out forwards" }}
                />
              </svg>
            </div>
          )}
        </div>

        {suggestRecalibrate && !faceLost && (
          <div style={recalibratePromptStyle}>
            <span>You were away for a moment — if you moved or changed seat, recalibrate.</span>
            <span style={{ marginLeft: "0.75rem", whiteSpace: "nowrap" }}>
              <button onClick={() => calibrateRef.current?.()} disabled={!ready || calibrating}>
                Recalibrate
              </button>
              <button onClick={() => setSuggestRecalibrate(false)} style={{ marginLeft: "0.4rem" }}>
                Dismiss
              </button>
            </span>
          </div>
        )}

        <p style={{ margin: "0.25rem 0" }}>{cameraStatus}</p>
        <p style={{ margin: "0.25rem 0" }}>
          Face detected: {faceDetected ? "Yes" : "No"} · Frames: {framesCollected} / 10
        </p>
        {lightingWarning && <p style={{ color: "orange", margin: "0.25rem 0" }}>{lightingWarning}</p>}

        <div style={{ margin: "0.5rem 0" }}>
          <button onClick={() => calibrateRef.current?.()} disabled={!ready || calibrating}>
            {calibrating ? "Calibrating..." : calibrated ? "Recalibrate" : "Calibrate Now"}
          </button>
          {calibrating && <span style={{ marginLeft: "0.75rem" }}>Look naturally at the screen...</span>}
          {calibrated && !calibrating && (
            <span style={{ marginLeft: "0.75rem", color: "green" }}>Calibrated</span>
          )}
        </div>
        {calibrationError && <p style={{ color: "red" }}>Calibration failed: {calibrationError}</p>}

        {prediction && (
          <>
            <p style={{ fontSize: "1.1rem", margin: "0.5rem 0" }}>
              <strong style={{ color: headlineColor }}>{headlineState}</strong>{" "}
              <span style={{ color: "#666", fontSize: "0.85rem" }}>
                ({(prediction.confidence * 100).toFixed(1)}%)
              </span>
              {headlineState !== prediction.state && (
                <span style={{ color: "#666", fontSize: "0.85rem" }}>
                  {" "}— underlying: {prediction.state}
                </span>
              )}
            </p>

            <details style={diagnosticsStyle}>
              <summary style={{ cursor: "pointer", color: "#666" }}>Diagnostics</summary>
              <div style={{ fontFamily: "monospace", fontSize: "0.78rem", color: "#777", textAlign: "left", marginTop: "0.5rem" }}>
                {prediction.raw_state && (
                  <div>
                    raw: {prediction.raw_state}{" — "}
                    {prediction.stable
                      ? "confirmed"
                      : `confirming (${prediction.streak}/${prediction.required})`}
                  </div>
                )}

                {prediction.fatigue_available === false && <div>fatigue: calibrate to enable</div>}
                {prediction.fatigue_available === true && (
                  <div>
                    fatigue: eyes low {Math.round(prediction.fatigue_ratio * 100)}% of 45s ·
                    {prediction.fatigue_pose_pitch !== null &&
                      prediction.fatigue_pose_pitch !== undefined
                      ? ` solvePnP pitch ${prediction.fatigue_pose_pitch}°`
                      : ` pitch Δ ${prediction.fatigue_pitch_delta} (recalibrate for solvePnP)`}
                    {prediction.fatigue_head_down && (
                      <strong style={{ color: "#0b6bcb" }}> ← looking down, window skipped</strong>
                    )}
                  </div>
                )}

                {prediction.furrow_off_pose && (
                  <div>furrow: head off-pose — reading not meaningful</div>
                )}
                {prediction.furrow_available && (
                  <div>
                    furrow: inter-brow {prediction.furrow_ratio} · brow-raise{" "}
                    {prediction.furrow_brow_ratio} (1.0 = baseline)
                    {prediction.furrowed && <strong style={{ color: "#0b6bcb" }}> ← furrowed</strong>}
                  </div>
                )}

                {/* Per-condition pass/fail: shows WHICH requirement blocks Deep
                    Thinking, instead of guessing at the thresholds again. */}
                {prediction.dt_available && (
                  <div>
                    deep-thinking:{" "}
                    <span style={{ color: prediction.dt_gaze_ok ? "green" : "#c00" }}>
                      gaze {prediction.dt_gaze_var.toExponential(2)}
                      {prediction.dt_gaze_ok ? " ok" : " HIGH"}
                    </span>{" · "}
                    <span style={{ color: prediction.dt_ear_ok ? "green" : "#c00" }}>
                      EAR {prediction.dt_ear_var.toExponential(2)}
                      {prediction.dt_ear_ok ? " ok" : " HIGH"}
                    </span>{" · "}
                    <span style={{ color: prediction.dt_pitch_ok ? "green" : "#c00" }}>
                      pitchΔ {prediction.dt_pitch_delta}
                      {prediction.dt_pitch_ok ? " ok" : " NOT DOWN"}
                    </span>{" · "}
                    <span style={{ color: prediction.dt_state_ok ? "green" : "#c00" }}>
                      state {prediction.dt_state_ok ? "ok" : "not Drifting/Struggling"}
                    </span>
                  </div>
                )}
              </div>
            </details>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}

# Frontend

React (Vite) client.

## Running it

```bash
cd frontend
npm install
cp .env.example .env      # then fill in the values
npm run dev
```

The backend must be running as well — see [`backend/README.md`](../backend/README.md).

`.env` needs the backend URL and the Firebase web config, both described in
[`.env.example`](.env.example). The Firebase values are public client
identifiers rather than secrets, but they stay out of git so each developer can
point at their own Firebase project.

## What is here so far

This scaffold was added by the Module 3 migration, because the engagement
capture loop had nowhere to live. It is deliberately thin.

| Path | Owner | Notes |
|---|---|---|
| `src/engagement/` | Module 3 | Camera, MediaPipe, windowing, backend calls |
| `src/pages/StudySession.jsx` | Module 3 | Rendering only |
| `src/api/client.js` | shared | Base URL and auth token injection |
| `src/auth/` | Module 1 | Firebase setup and profile loading |
| `src/App.jsx` | placeholder | Sign in, then the study session |

**`App.jsx` is not a routing decision.** It exists so the webcam-to-engagement
pipeline can be run end to end. The Module 1 frontend migration — registration,
role-based dashboards, accessibility settings, protected routes — will replace
it rather than build on it.

## Module 3: how the capture loop is arranged

The prototype had all of this in one 630-line page. It is split here so the
parts that matter can be read and tested on their own:

- **`engagement/constants.js`** — window size, capture rate, thresholds. Several
  of these have to agree with the backend; changing one produces wrong
  predictions rather than an error, which is why they are in one place.
- **`engagement/landmarks.js`** — MediaPipe results to `[[x, y, z], ...]`, plus
  the brightness check. No React, so it can be unit tested.
- **`engagement/faceLandmarker.js`** — creating and disposing the landmarker.
  The model and WASM runtime are pinned to exact versions, because the LSTM was
  fitted on features derived from this landmark model.
- **`engagement/api.js`** — the four engagement endpoints.
- **`engagement/useEngagementCapture.js`** — the loop: camera, rolling window,
  calibration, and teardown.
- **`engagement/useFacePresence.js`** — debounced "learner is out of frame".

### Two behaviours worth knowing about

**Cleanup is load-bearing.** `main.jsx` uses `StrictMode`, which runs effects
twice in development on purpose. Without full teardown — interval, animation
frame, camera tracks, landmarker — two capture loops ran at once and frames
arrived at roughly double the rate the model expects, which quietly changes
what a "10 second window" means.

**Overlapping requests are dropped, not queued.** Windows are produced once a
second but a request can take longer than that. The rule detectors assume
windows arrive in order, so a second request is skipped while one is in flight;
a window already stale by the time it would be sent has nothing to add. The
count of skipped windows appears in the diagnostics panel. The backend enforces
the same thing per session, so a second browser tab cannot bypass it.

### Privacy

The camera image never leaves the browser. It is not stored, buffered, or
uploaded — what crosses the network is a list of numbers. The camera is not
requested until the learner dismisses the instructions dialog. Full detail in
[`docs/privacy/webcam-data-handling.md`](../docs/privacy/webcam-data-handling.md).

### The diagnostics panel

The panel under the engagement state is a development instrument. Scope section
6.8 requires that no scores or state indicators are shown during an active
session in the finished product, so it comes out before any learner-facing
release.

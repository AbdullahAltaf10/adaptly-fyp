# Adaptly — Legacy Prototype (Modules 1–3)

**Archive branch. Do not merge into `develop` or `main`.**

A snapshot of the original working prototype, preserved for reference during
migration to the shared project structure. It is a point-in-time copy, not an
actively maintained branch.

## What this contains

| Module | State |
|---|---|
| **1 — User Profile & Access Management** | Firebase auth (Email/Password + Google), MongoDB profiles, role/mode route guards, accessibility settings |
| **2 — Content Processing** | PDF, research paper (column-aware), plain text, website URL, YouTube transcript. Video transcription is coded but dormant without an API key |
| **3 — Real-Time Engagement Detection** | MediaPipe landmarks → 9 engineered features → trained LSTM (3 states), per-user calibration, plus rule-based Fatigued / Recovered / Deep Thinking detectors and temporal smoothing |

Note the structure here predates the shared layout on `develop`: this prototype
uses `backend/app/{core,ml,models,routes,services}` rather than
`backend/app/{api,auth,content,core,engagement,users}`. Migration will need to
map between the two.

## Configuration required (nothing secret is committed)

No real credentials exist anywhere in this branch or its history. To run it you
must supply your own:

1. **`backend/.env`** — copy from `backend/.env.example`. Needs a MongoDB Atlas
   URI and database name.
2. **`frontend/.env`** — copy from `frontend/.env.example`. Needs your Firebase
   web config and the backend URL.
3. **`backend/app/core/firebase-service-account.json`** — download from the
   Firebase console (Project settings → Service accounts). Gitignored.

## How it was intended to run

**Backend** — from `backend/`:
```bash
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload    # must be run from backend/, not from app/
```

**Frontend** — from `frontend/`:
```bash
npm install
npm run dev                      # expects http://localhost:5173
```

Then register an account, upload content, and open Study Session. The webcam
requires a one-time **Calibrate** before engagement readings are meaningful.

## Things that will waste your time if you don't know them

- **`certifi` is required for MongoDB Atlas on Windows.** Without
  `tlsCAFile=certifi.where()`, writes silently fail to appear in Atlas with no
  error.
- **Windows clock drift causes Firebase 401s** reading `Token used too early`.
  Fix with Settings → Time & Language → Sync now.
- **Never run `npm audit fix --force`** — it upgraded Vite past the installed
  Node version and broke the project.
- Calibration is **per user and per camera angle**. Several people testing under
  one login share one baseline, so each must recalibrate.
- Engagement predictions lag real behaviour by roughly 10 seconds. This is
  structural — the model reads a rolling 10-frame window at 1 frame/sec — not a
  bug to be fixed by tuning.

## Known limitations, stated honestly

- **Struggling detection is weak (10–18% recall).** This is a documented hard
  problem in published DAiSEE research, not an implementation defect. A trivial
  "always guess Focused" baseline scores 84.7% raw accuracy on the same data, so
  **accuracy is a misleading metric here** — judge it on per-class recall.
- Head pose uses a simplified geometric approximation for the model's features
  rather than `solvePnP`, which the scope document specifies. `solvePnP` is used
  by the rule-based detectors only; swapping it into the model's features
  requires a full retrain.
- The Deep Thinking detector's thresholds are estimates, not measured values.
- Rule-state is held in memory per session and does not survive a restart or
  work across multiple server workers.
- Not built: the OneStop re-reading classifier, WebSocket streaming, and
  Modules 4–12.

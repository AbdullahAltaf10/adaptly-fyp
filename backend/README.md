# Adaptly — Backend

FastAPI service handling authentication, content processing and engagement
detection.

## Requirements

- **Python 3.12** (developed and tested on 3.12.3)
- MongoDB Atlas cluster
- Firebase project with Authentication enabled

## Setup

### 1. Virtual environment

From `backend/`:

```bash
python -m venv venv
venv\Scripts\Activate.ps1     # Windows PowerShell
# source venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
```

The virtual environment must be activated in **every new terminal session**.

> Installing TensorFlow pulls roughly 500 MB of dependencies, so the first
> install is slow. This is expected.

### 2. MongoDB

1. Create a free cluster at <https://cloud.mongodb.com>.
2. **Database Access** → add a user with read/write permissions.
3. **Network Access** → allow your IP (or `0.0.0.0/0` for development only).
4. **Connect → Drivers** → copy the connection string into `MONGO_URI`.

Collections (`users`, `content`, `calibration`) are created automatically on
first write; no manual setup is needed.

> **Windows note:** Atlas requires `certifi`, already pinned in
> `requirements.txt`. Without `tlsCAFile=certifi.where()` in the Mongo client,
> writes fail **silently** — no error, but nothing appears in Atlas.

### 3. Firebase Admin

The backend verifies the Firebase ID token sent by the frontend on every
request, which requires a service-account key.

1. Firebase console → **Project settings → Service accounts**.
2. **Generate new private key** → downloads a JSON file.
3. Save it as `backend/app/core/firebase-service-account.json`.

This file is a **real credential**. It is gitignored and must never be
committed or shared.

> If tokens are rejected with `Token used too early`, your system clock has
> drifted. On Windows: **Settings → Time & Language → Sync now**.

### 4. Environment variables

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `MONGO_URI` | yes | MongoDB Atlas connection string |
| `DB_NAME` | yes | Database name (e.g. `adaptly`) |
| `OPENAI_API_KEY` | no | Video transcription only; endpoint returns 503 without it |

## Running

From `backend/`, with the virtual environment active:

```bash
uvicorn app.main:app --reload
```

Serves on <http://127.0.0.1:8000>; interactive API docs at `/docs`.

> Run this from `backend/`, **not** from inside `app/` — the `app.main` import
> path resolves relative to `backend/`.

Check it started: <http://127.0.0.1:8000/health> should return
`{"status": "ok"}`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` after install | virtual environment not activated | `venv\Scripts\Activate.ps1` |
| `Token used too early` | system clock drift | sync your clock |
| Writes succeed but nothing in Atlas | missing `certifi` TLS config | ensure `tlsCAFile=certifi.where()` |
| `InconsistentVersionWarning` on startup | scikit-learn differs from the version that trained the scaler | align the pinned `scikit-learn` version |
| Frontend shows "Network Error" | backend not running, or its origin is not in the CORS allowlist | start the backend; check `allow_origin_regex` in `app/main.py` |
| `503` from the video upload endpoint | `OPENAI_API_KEY` not set | expected — set the key to enable it |

## Security

Never commit: `.env`, `firebase-service-account.json`, `venv/`, or
`__pycache__/`. All are covered by `.gitignore`.

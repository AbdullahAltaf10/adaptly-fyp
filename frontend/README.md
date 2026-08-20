# Adaptly frontend

This Vite/React frontend currently contains the Module 5 assistant chat panel.
It uses isolated demo study context until content, session, and learner-profile
modules are connected.

## Install and run

```bash
cd frontend
npm install
npm run dev
```

The development server runs at `http://127.0.0.1:5173` by default.

## Backend URL

Copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` when the backend
does not run at `http://127.0.0.1:8000`.

Run the backend separately:

```bash
cd backend
python3 -m uvicorn app.main:app --reload
```

The frontend calls `POST /api/v1/assistant/messages`. It derives
`previous_messages` from visible learner/assistant messages and never calls
Gemini directly. Gemini credentials must remain in the backend environment.

Suggested questions populate the input for learner review before sending. The
demo context lives in `src/features/ai-assistant/demoStudyContext.js` and must
be replaced by real study-session data when upstream modules are integrated.

## Voice interaction

Voice input uses the browser's Web Speech API (`SpeechRecognition` or
`webkitSpeechRecognition`) to place a recognised transcript into the editable
question field. It is not sent as audio to Adaptly or Gemini. Web Speech API
support varies by browser, so typed chat remains fully available when voice
input is unavailable.

Assistant answers can be played with the browser's `speechSynthesis` API. The
optional **Voice responses** toggle is off by default; enabling it speaks new
assistant answers after they appear. This is live browser speech only, not
downloadable or stored Module 7 audio. Gemini credentials remain backend-only.

## Test

```bash
npm test
```

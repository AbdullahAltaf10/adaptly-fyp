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

The frontend calls `POST /api/v1/assistant/messages`. Every request passes the
current `session_id`, `content_id`, `current_chunk`, learner question, and only
completed learner/assistant messages as `previous_messages`. It never calls
Gemini directly; Gemini credentials must remain in the backend environment.

After a successful API response, the panel renders the backend-provided three
`suggested_questions`; clicking one populates the regular input for review and
sending through the same request path. The backend is also the source of the
request-scoped `emotion_signal`; it is not shown as a learner label.

`AssistantPanel` accepts a `studyContext` prop as the integration boundary for
the active session/content/chunk. This standalone frontend currently passes the
clearly isolated fallback in `src/features/ai-assistant/demoStudyContext.js`
because no upstream study-session provider exists yet. Replace that App-level
fallback with real active context when Modules 1–2/session UI are integrated;
do not generate a new session ID per message. Switching sections supplies a
new current chunk on the next request. A session change clears local visible
conversation to prevent cross-session history mixing.

If the backend is unavailable, returns a provider/configuration error, or
returns malformed data, the panel keeps visible conversation intact, shows a
safe retry action, and never exposes provider internals.

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

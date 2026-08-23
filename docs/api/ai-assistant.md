# Module 5 Assistant API Foundation

## Purpose

This API is the foundation for Adaptly's Module 5 Context-Aware AI Assistant.
It validates a learner question and context, then returns a deterministic local
mock response or a Gemini-generated answer, depending on backend configuration.

## Endpoint

`POST /api/v1/assistant/messages`

## Request

```json
{
  "question": "Can you explain this paragraph more simply?",
  "session_id": "session-001",
  "content_id": "content-001",
  "current_chunk": {
    "chunk_id": "chunk-003",
    "text": "Gradient descent updates model parameters to reduce error.",
    "section_title": "Model Training"
  },
  "content_context": {
    "title": "Introduction to Machine Learning",
    "content_type": "pdf",
    "language": "en"
  },
  "session_context": {
    "status": "active",
    "current_chunk_id": "chunk-003"
  },
  "learner_preferences": {
    "preferred_explanation_mode": "simple"
  },
  "previous_messages": [
    {
      "role": "user",
      "message": "What is a neural network?"
    },
    {
      "role": "assistant",
      "message": "A neural network is a machine-learning model."
    }
  ]
}
```

`question`, `session_id`, `content_id`, and `current_chunk` are required.
`current_chunk` requires `chunk_id` and `text`; `section_title` is optional.
`content_context`, `session_context`, and `learner_preferences` are optional.
Content context may provide `title`, `content_type`, and `language`. Session
context may provide `status` and `current_chunk_id`. Learner preferences may
provide `preferred_explanation_mode` (`standard`, `simple`, or `detailed`) and
`preferred_content_mode` (`text`, `audio`, or `mixed`). These values only adjust
the explanation style; they do not enable voice features.
`previous_messages` is optional and defaults to an empty list. Each previous
message must have role `user` or `assistant` and a non-empty `message`.

## Response

```json
{
  "answer": "Mock assistant response for chunk 'chunk-003' in the 'Model Training' section. Your question was received with the current learning context.",
  "emotion_signal": "neutral",
  "used_context": true,
  "response_mode": "text",
  "session_id": "session-001",
  "content_id": "content-001",
  "chunk_id": "chunk-003"
}
```

`emotion_signal` is always one of `neutral`, `confusion`, or `frustration`.
It is a lightweight conversational support signal derived only from the current
learner message, not a clinical or psychological assessment. The signal is
request-scoped: it is not persisted, accumulated into a profile, or inferred
from webcam, voice, biometric, or engagement data. It is exposed for a future
Module 6 integration; this API does not make interventions from it.

## Validation

All strings are trimmed. Empty or whitespace-only values are rejected with
FastAPI's standard 422 validation response. IDs are limited to 128 characters,
questions to 2,000 characters, chunk text to 12,000 characters, individual
previous messages to 4,000 characters, and conversation history to 20 messages.
Unknown fields and previous-message roles other than `user` and `assistant` are
rejected.

## Context and conversation memory

Each request builds a normalized context from the required content/session IDs,
active chunk, optional metadata, preferences, and supplied conversation history.
The active chunk remains the detailed source context, so a question such as
`What does this mean?` can be interpreted against the current chunk and recent
discussion.

Conversation context is request-scoped and session-scoped: no global history is
kept and no database persistence is implemented in this issue. The prompt uses a
deduplicated window of at most eight messages. It prioritizes recent messages,
keeps chronological order, and retains the first learner question when it would
otherwise be dropped by the window. Durable session memory will be added only
when a session persistence layer exists. Until then, the client must supply only
history from the request's `session_id`; messages do not yet carry separate
session identifiers that the backend can verify.

## Assistant modes and Gemini configuration

`ASSISTANT_MODE` selects `mock` (the default) or `gemini` mode. Mock mode is
deterministic, makes no external call, and requires no API key, so it is used in
tests and offline development.

Gemini mode uses the official Google Gen AI Python SDK and requires
`GEMINI_API_KEY` in the backend environment. `GEMINI_MODEL` defaults to
`gemini-3.6-flash`; `GEMINI_TIMEOUT_MS` defaults to 60,000 milliseconds and may
be set between 1 and 120,000. A missing key or invalid configuration returns
HTTP 503. A provider failure or unusable response returns HTTP 502. A timeout
returns HTTP 504. These responses do not include provider details or secrets.

The prompt gives Gemini the learner question, active learning chunk, optional
section title, and previous messages. Adaptly uses the local conversational
support signal to request simpler steps for confusion or a brief respectful
acknowledgement and one-step-at-a-time guidance for frustration. It makes no
second Gemini call to derive this signal. Core assistant instructions are separated
from all supplied values, which are labelled untrusted data; instructions inside
the content or conversation do not override Adaptly's learning-assistant rules.

## Privacy

This endpoint does not accept raw webcam video, webcam frames, facial landmarks,
or engagement telemetry, and it does not persist conversation data. Mock mode
keeps assistant input local. In Gemini mode, only the supplied educational
context (question, active chunk, optional metadata/preferences, and bounded
conversation window) is sent to Google's Gemini service; no raw webcam data is
sent.

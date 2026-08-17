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
`previous_messages` is optional and defaults to an empty list. Each previous
message must have role `user` or `assistant` and a non-empty `message`.

## Response

```json
{
  "answer": "Mock assistant response for chunk 'chunk-003' in the 'Model Training' section. Your question was received with the current learning context.",
  "used_context": true,
  "response_mode": "text",
  "session_id": "session-001",
  "content_id": "content-001",
  "chunk_id": "chunk-003"
}
```

## Validation

All strings are trimmed. Empty or whitespace-only values are rejected with
FastAPI's standard 422 validation response. IDs are limited to 128 characters,
questions to 2,000 characters, chunk text to 12,000 characters, individual
previous messages to 4,000 characters, and conversation history to 20 messages.
Unknown fields and previous-message roles other than `user` and `assistant` are
rejected.

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
section title, and previous messages. Core assistant instructions are separated
from all supplied values, which are labelled untrusted data; instructions inside
the content or conversation do not override Adaptly's learning-assistant rules.

## Privacy

This endpoint does not accept raw webcam video, webcam frames, or engagement
telemetry, and it does not persist conversation data. Mock mode keeps assistant
input local. In Gemini mode, the supplied question, active chunk, and previous
conversation messages are sent to Google's Gemini service; no raw webcam data
is sent.

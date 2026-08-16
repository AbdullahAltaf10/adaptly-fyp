# Module 5 Assistant API Foundation

## Purpose

This API is the Issue #17 foundation for Adaptly's Module 5 Context-Aware AI
Assistant. It validates a learner question and its current learning context,
then returns a deterministic local mock response.

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

## Mock mode

Issue #17 intentionally uses a deterministic local mock service. No Gemini API
key, external AI call, database, or internet connection is required. Gemini
integration belongs to Issue #18.

## Privacy

This endpoint does not accept raw webcam video, webcam frames, or engagement
telemetry. In Issue #17 it does not send learning content to any external AI
service and does not persist conversation data.

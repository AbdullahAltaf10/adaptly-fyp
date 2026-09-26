"""
Pure construction of Module 8 assistant-event pairs for one exchange (Issue #34).

No I/O, no MongoDB, no FastAPI. `build_assistant_events` takes what the route
handler already has in scope - the validated request, the caller's user_id
(from auth), how the question arrived, and the outcome of calling
`service.create_assistant_response` - and returns two contract-shaped dicts:
one `direction="learner"` event describing the question, one
`direction="assistant"` event describing the response (or the failure, if
the provider call didn't succeed). Writing them is a separate, fail-silent
concern, the same split `engagement/contracts.py` (pure) and
`engagement/analytics_sink.py` (I/O) already establish for Module 3.

Two events per exchange, not one
---------------------------------
shared/contracts/assistant-event.schema.json's `direction` enum
(learner|assistant) exists because Module 8's metric engine
(`domain/metrics.py::calculate_assistant_usage`, Issue #26, already merged)
filters assistant events by `direction` to compute `learner_message_count`
and `assistant_message_count` separately. One merged event per exchange
cannot feed that calculation correctly, so an exchange is always two rows
here - not a stylistic choice, a requirement of already-shipped code.

Two fields DO have a "not applicable to this direction" slot
--------------------------------------------------------------
`input_mode` and `response_mode` both have a real `not_applicable` value in
the contract for exactly this situation: a learner event has no
`response_mode`, an assistant event has no `input_mode`.

Three fields do NOT have an equivalent slot
---------------------------------------------
`suggested_question_used`, `intent`, and `learner_signal` have no neutral
"doesn't apply to this direction" value available (a plain boolean, and two
enums with no `not_applicable` member). This mirrors the same value onto
both events, on the reasoning that each describes a property of the whole
exchange rather than of one side of it. This is a judgement call, not
something the contract dictates - flagged here and in the Issue #34 PR
description for review.

`intent` is always "unknown"
------------------------------
No real intent classification exists in Module 5 today. `"unknown"` is a
valid enum member for exactly this situation, and using it is a documented
placeholder, not a bug - do not read it as a real signal until a classifier
is built.

`learner_signal` is computed from the question text directly
----------------------------------------------------------------
Rather than reading it off a (possibly absent, if the provider call failed)
`AssistantMessageResponse`, this recomputes it here via
`classify_conversational_signal(request.question)` - the same function
`service.py` itself calls, and something that is always available regardless
of whether the exchange succeeded. A learner's question can be classified as
confused or frustrated even when Gemini never returns a usable answer to it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from app.ai_assistant.schemas import AssistantMessageRequest, AssistantMessageResponse
from app.ai_assistant.signals import classify_conversational_signal

SCHEMA_VERSION = "1.0"

InputMode = Literal["typed", "voice", "suggested_question"]
ExchangeStatus = Literal["success", "error"]


def _event_id() -> str:
    return str(uuid.uuid4())


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_assistant_events(
    request: AssistantMessageRequest,
    *,
    user_id: str,
    input_mode: InputMode,
    status: ExchangeStatus,
    error_code: str | None = None,
    model_name: str | None = None,
    response: AssistantMessageResponse | None = None,
) -> tuple[dict, dict]:
    """Build the (learner_event, assistant_event) pair for one exchange.

    `response` is the successful `AssistantMessageResponse`, or `None` if the
    provider call failed. `status`/`response` must agree: `status="success"`
    requires a `response`; `status="error"` requires `response=None`. This is
    enforced rather than left to produce a contract-shaped but nonsensical
    document (a "successful" event with no response, or an "error" event
    that also claims a response mode).

    `model_name` is the Gemini model that was attempted, or `None` in mock
    mode, or when the mode couldn't be determined before the failure.
    """

    if status == "success" and response is None:
        raise ValueError("status='success' requires a response")
    if status == "error" and response is not None:
        raise ValueError("status='error' must not carry a response")

    learner_signal = classify_conversational_signal(request.question)
    suggested_question_used = input_mode == "suggested_question"
    response_mode = response.response_mode if response is not None else "not_applicable"

    common = {
        "schema_version": SCHEMA_VERSION,
        "session_id": request.session_id,
        "user_id": user_id,
        "content_id": request.content_id,
        "chunk_id": request.current_chunk.chunk_id,
        "intent": "unknown",
        "learner_signal": learner_signal,
        "suggested_question_used": suggested_question_used,
    }

    learner_event = {
        **common,
        "event_id": _event_id(),
        "timestamp": _timestamp(),
        "direction": "learner",
        "input_mode": input_mode,
        "response_mode": "not_applicable",
        "status": "success",
        "error_code": None,
        "model_name": None,
        "model_version": None,
    }

    assistant_event = {
        **common,
        "event_id": _event_id(),
        "timestamp": _timestamp(),
        "direction": "assistant",
        "input_mode": "not_applicable",
        "response_mode": response_mode,
        "status": status,
        "error_code": error_code,
        "model_name": model_name,
        "model_version": None,
    }

    return learner_event, assistant_event

"""HTTP endpoint for the Module 5 assistant foundation."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai_assistant.analytics_contracts import build_assistant_events
from app.ai_assistant.analytics_sink import record_assistant_exchange
from app.content.glossary import glossary_for
from app.engagement import latest_state
from app.ai_assistant import history_store
from app.ai_assistant.schemas import (
    AssistantMessageRequest,
    AssistantMessageResponse,
    HistoryMessage,
    HistoryResponse,
    MAX_HISTORY_LIMIT,
    SuggestionsRequest,
    SuggestionsResponse,
)
from app.ai_assistant import service
from app.ai_assistant.suggestions import suggest_for_chunk
from app.auth.dependencies import get_current_user


router = APIRouter(prefix="/assistant", tags=["ai-assistant"])


@router.post("/suggestions", response_model=SuggestionsResponse)
def create_suggestions(
    request: SuggestionsRequest,
    user: dict = Depends(get_current_user),
) -> SuggestionsResponse:
    """Questions worth asking about the paragraph the learner is on.

    Separate from /messages so the panel can refresh its suggestions when the
    learner scrolls to a new paragraph, without asking a question first. Purely
    local (see suggestions.py): no model call, so no quota and no failure mode
    beyond auth.
    """
    return SuggestionsResponse(suggested_questions=suggest_for_chunk(request.current_chunk))


@router.get("/history", response_model=HistoryResponse)
def get_history(
    limit: int = 50,
    before: float | None = None,
    user: dict = Depends(get_current_user),
) -> HistoryResponse:
    """The learner's own persistent assistant conversation, newest first."""
    bounded_limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    raw = history_store.list_messages(user["uid"], limit=bounded_limit, before=before)
    return HistoryResponse(
        messages=[
            HistoryMessage(
                id=doc["_id"],
                role=doc["role"],
                content=doc["content"],
                source=doc["source"],
                trigger=doc.get("trigger"),
                content_id=doc.get("content_id"),
                chunk_id=doc.get("chunk_id"),
                session_id=doc.get("session_id"),
                timestamp=doc["timestamp"],
            )
            for doc in raw
        ]
    )


def _record_exchange_safely(*args, **kwargs) -> None:
    """Analytics is a side effect and must never affect the response.

    `record_assistant_exchange` already fails silently against a database
    problem; this also guards `build_assistant_events` itself (a bug there
    would otherwise raise here, in the middle of returning a response or
    handling an unrelated exception). Either way, nothing raised in here is
    allowed to mask or replace what the caller is already returning/raising.
    """
    try:
        learner_event, assistant_event = build_assistant_events(*args, **kwargs)
        record_assistant_exchange(learner_event, assistant_event)
    except Exception:
        pass


@router.post("/messages", response_model=AssistantMessageResponse)
def create_assistant_message(
    request: AssistantMessageRequest,
    user: dict = Depends(get_current_user),
) -> AssistantMessageResponse:
    """Return a mock or Gemini-backed response for a learner question."""
    # Deliberately not done: every error branch below records model_name=None,
    # even for AssistantProviderError/AssistantProviderTimeoutError, where a
    # real Gemini call was actually attempted. service.py's exception paths
    # don't currently carry the attempted model name back out to the caller -
    # threading it through would mean widening create_assistant_response's
    # error handling, which is more than this issue's wiring needs. A missing
    # model_name on a failed exchange is honest (we don't have it here), not
    # a bug to silently work around.
    try:
        response, model_name = service.create_assistant_response(
            request,
            # Read on the server, keyed on the caller's own uid, so it can
            # neither be forged by the request nor leak between learners.
            engagement_state=latest_state.get(user["uid"], request.session_id),
            # Module 2 prepared this at ingestion so the agent can explain a
            # term instantly (scope 6.2). Read here rather than taken from
            # the request, for the same reason as the engagement state.
            glossary=glossary_for(request.content_id),
        )
    except service.AssistantConfigurationError as error:
        _record_exchange_safely(
            request,
            user_id=user["uid"],
            input_mode=request.input_mode,
            status="error",
            error_code="AssistantConfigurationError",
            model_name=None,
            response=None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assistant service is not configured.",
        ) from error
    except service.AssistantProviderTimeoutError as error:
        _record_exchange_safely(
            request,
            user_id=user["uid"],
            input_mode=request.input_mode,
            status="error",
            error_code="AssistantProviderTimeoutError",
            model_name=None,
            response=None,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Assistant provider timed out. Please try again.",
        ) from error
    except service.AssistantProviderError as error:
        _record_exchange_safely(
            request,
            user_id=user["uid"],
            input_mode=request.input_mode,
            status="error",
            error_code="AssistantProviderError",
            model_name=None,
            response=None,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Assistant provider is temporarily unavailable. Please try again.",
        ) from error

    _record_exchange_safely(
        request,
        user_id=user["uid"],
        input_mode=request.input_mode,
        status="success",
        model_name=model_name,
        response=response,
    )
    history_store.insert_message(
        uid=user["uid"],
        role="user",
        content=request.question,
        source=request.source,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
        session_id=request.session_id,
    )
    history_store.insert_message(
        uid=user["uid"],
        role="assistant",
        content=response.answer,
        source=request.source,
        content_id=request.content_id,
        chunk_id=request.current_chunk.chunk_id,
        session_id=request.session_id,
    )
    return response

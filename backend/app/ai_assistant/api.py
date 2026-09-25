"""HTTP endpoint for the Module 5 assistant foundation."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai_assistant.analytics_contracts import build_assistant_events
from app.ai_assistant.analytics_sink import record_assistant_exchange
from app.ai_assistant.schemas import AssistantMessageRequest, AssistantMessageResponse
from app.ai_assistant import service
from app.auth.dependencies import get_current_user


router = APIRouter(prefix="/assistant", tags=["ai-assistant"])


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
        response, model_name = service.create_assistant_response(request)
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
    return response

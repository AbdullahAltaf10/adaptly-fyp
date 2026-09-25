"""HTTP endpoint for the Module 5 assistant foundation."""

from fastapi import APIRouter, HTTPException, status

from app.ai_assistant.schemas import AssistantMessageRequest, AssistantMessageResponse
from app.ai_assistant import service


router = APIRouter(prefix="/assistant", tags=["ai-assistant"])


@router.post("/messages", response_model=AssistantMessageResponse)
def create_assistant_message(
    request: AssistantMessageRequest,
) -> AssistantMessageResponse:
    """Return a mock or Gemini-backed response for a learner question."""
    try:
        return service.create_assistant_response(request)
    except service.AssistantConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assistant service is not configured.",
        ) from error
    except service.AssistantProviderTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Assistant provider timed out. Please try again.",
        ) from error
    except service.AssistantProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Assistant provider is temporarily unavailable. Please try again.",
        ) from error

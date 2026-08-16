"""HTTP endpoint for the Module 5 assistant foundation."""

from fastapi import APIRouter

from app.ai_assistant.schemas import AssistantMessageRequest, AssistantMessageResponse
from app.ai_assistant.service import create_mock_response


router = APIRouter(prefix="/assistant", tags=["ai-assistant"])


@router.post("/messages", response_model=AssistantMessageResponse)
def create_assistant_message(
    request: AssistantMessageRequest,
) -> AssistantMessageResponse:
    """Return a deterministic local mock response for a learner question."""
    return create_mock_response(request)

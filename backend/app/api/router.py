"""Top-level API router registration."""

from fastapi import APIRouter

from app.ai_assistant.api import router as assistant_router


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(assistant_router)

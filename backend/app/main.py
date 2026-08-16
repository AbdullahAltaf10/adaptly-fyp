"""FastAPI application entry point for the Adaptly backend."""

from fastapi import FastAPI

from app.api.router import api_router


app = FastAPI(
    title="Adaptly Backend API",
    version="0.1.0",
    description="Backend API for the Adaptly learning platform.",
)
app.include_router(api_router)

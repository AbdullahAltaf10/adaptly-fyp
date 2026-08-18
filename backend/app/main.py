"""FastAPI application entry point for the Adaptly backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router


app = FastAPI(
    title="Adaptly Backend API",
    version="0.1.0",
    description="Backend API for the Adaptly learning platform.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)
app.include_router(api_router)

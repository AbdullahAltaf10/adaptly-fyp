from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router

app = FastAPI(title="Adaptly API")

app.add_middleware(
    CORSMiddleware,
    # Vite moves to the next free port (5174, 5175, ...) whenever 5173 is taken,
    # and the browser treats localhost and 127.0.0.1 as different origins.
    # Pinning one exact origin meant either situation broke every API call with
    # an opaque "Network Error" that looked like an auth problem.
    # TIGHTEN THIS to the real deployed origin before going to production.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}

import app.core.paths  # noqa: F401  - puts repo root on sys.path for `ml`

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.engagement.warmup import warm_models_in_background


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Returns at once: the models load on a daemon thread, so the server still
    # accepts connections immediately. See app/engagement/warmup.py.
    warm_models_in_background()
    yield


app = FastAPI(title="Adaptly API", lifespan=lifespan)

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

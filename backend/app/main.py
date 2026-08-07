from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.dependencies import get_current_user
from app.routes.user_routes import router as user_router
from app.routes.content_routes import router as content_router
from app.routes.engagement_routes import router as engagement_router

app = FastAPI(title="Adaptly API")

app.add_middleware(
    CORSMiddleware,
    # Vite silently moves to the next free port (5174, 5175, ...) whenever 5173
    # is already taken, and the browser treats localhost and 127.0.0.1 as
    # different origins. Pinning one exact origin meant any of those situations
    # broke every API call with an opaque "Network Error".
    # TIGHTEN THIS to the real deployed origin before going to production.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(content_router)
app.include_router(engagement_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/me")
def read_current_user(user=Depends(get_current_user)):
    return {"uid": user["uid"], "email": user.get("email")}
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv

# Load environment variables from .env (project or backend directory) BEFORE importing routers
try:
    # Try current working directory first
    load_dotenv()
    # Also try backend/.env relative to this file if not already loaded
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(os.path.dirname(here), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
except Exception:
    # Non-fatal
    pass

from app.api.review import router as review_router
from app.api.metrics import router as metrics_router
from app.db.session import db_enabled, session_scope

app = FastAPI(title="OCR2 Backend", version="0.1.0")

# CORS for development: allow Vite dev server and same-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for dev; tighten in prod or use env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review_router)
app.include_router(metrics_router)

# Static files for uploaded images
def _upload_root() -> str:
    return os.getenv("UPLOAD_DIR", os.path.join("backend", "uploads"))

os.makedirs(_upload_root(), exist_ok=True)
app.mount("/files", StaticFiles(directory=_upload_root()), name="files")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict:
    enabled = db_enabled()
    if not enabled:
        return {"enabled": False}
    try:
        # Simple query to validate session
        from sqlalchemy import text
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        return {"enabled": True, "connection": "ok"}
    except Exception as e:
        return {"enabled": True, "connection": "error", "detail": str(e)}

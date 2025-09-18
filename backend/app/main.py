from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.api.review import router as review_router

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

# Static files for uploaded images
def _upload_root() -> str:
    return os.getenv("UPLOAD_DIR", os.path.join("backend", "uploads"))

os.makedirs(_upload_root(), exist_ok=True)
app.mount("/files", StaticFiles(directory=_upload_root()), name="files")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

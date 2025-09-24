from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv
import time
import json

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
from app.api import batches as batches_router_module

app = FastAPI(title="OCR2 Backend", version="0.1.0")

# CORS from env ALLOWED_ORIGINS (comma-separated). Defaults to dev permissive if not set
allowed = os.getenv("ALLOWED_ORIGINS")
allow_origins = [o.strip() for o in allowed.split(",") if o.strip()] if allowed else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Simple in-proc rate limiter middleware (token bucket per IP)
RATE_RPS = float(os.getenv("RATE_LIMIT_RPS", "5"))
RATE_BURST = float(os.getenv("RATE_LIMIT_BURST", "10"))
_buckets: dict[str, tuple[float, float]] = {}

def set_rate_limit(rps: float | None = None, burst: float | None = None, clear_buckets: bool = True) -> None:
    """Testing helper to tune rate limiter deterministically.

    Note: safe to call at runtime; affects subsequent requests only.
    """
    global RATE_RPS, RATE_BURST, _buckets
    if rps is not None:
        RATE_RPS = float(rps)
    if burst is not None:
        RATE_BURST = float(burst)
    if clear_buckets:
        _buckets.clear()

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/health") or path.startswith("/files"):
        return await call_next(request)
    try:
        ip = request.client.host if request.client else "unknown"
    except Exception:
        ip = "unknown"
    now = time.time()
    tokens, last = _buckets.get(ip, (RATE_BURST, now))
    # Refill
    tokens = min(RATE_BURST, tokens + (now - last) * RATE_RPS)
    if tokens < 1.0:
        return JSONResponse(status_code=429, content={"detail": "rate_limited"})
    tokens -= 1.0
    _buckets[ip] = (tokens, now)
    return await call_next(request)


# Structured logging with request_id and correlation_id
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.time()
    req_id = request.headers.get("X-Request-ID") or hex(int(start * 1e9))[-12:]
    # Correlation from header or query param
    corr = request.headers.get("X-Correlation-ID") or request.query_params.get("correlation_id")
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        log = {
            "level": "info",
            "msg": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "request_id": req_id,
            "correlation_id": corr,
            "client": request.client.host if request.client else None,
            "ua": request.headers.get("user-agent"),
        }
        print(json.dumps(log, ensure_ascii=False))
        response.headers["X-Request-ID"] = req_id
        if corr:
            response.headers["X-Correlation-ID"] = corr
        return response
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log = {
            "level": "error",
            "msg": "request_error",
            "method": request.method,
            "path": request.url.path,
            "duration_ms": duration_ms,
            "request_id": req_id,
            "correlation_id": corr,
            "error": str(e),
        }
        print(json.dumps(log, ensure_ascii=False))
        raise

app.include_router(review_router)
app.include_router(metrics_router)
app.include_router(batches_router_module.router)

# Static files for uploaded images
def _upload_root() -> str:
    return os.getenv("UPLOAD_DIR", os.path.join("backend", "uploads"))

os.makedirs(_upload_root(), exist_ok=True)
app.mount("/files", StaticFiles(directory=_upload_root()), name="files")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/health/db")
def health_db() -> dict:
    enabled = db_enabled()
    if not enabled:
        return {"enabled": False}
    try:
        # Simple query to validate session
        from sqlalchemy import text
        t0 = time.time()
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        ms = int((time.time() - t0) * 1000)
        return {"enabled": True, "connection": "ok", "ping_ms": ms, "version": app.version}
    except Exception as e:
        return {"enabled": True, "connection": "error", "detail": str(e)}

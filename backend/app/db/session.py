from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from sqlalchemy.pool import NullPool

# Do NOT create the engine/sessionmaker at import time to allow tests to
# toggle DATABASE_URL dynamically. We also purposely avoid defining module
# attributes named `_engine` / `_SessionLocal` so that module-level __getattr__
# can serve dynamic values reflecting the latest environment.
_current_url: str | None = None


def _configure_if_needed() -> None:
    global _current_url
    url = os.getenv("DATABASE_URL")
    if url == _current_url:
        return
    # URL changed (or toggled to/from None): rebuild engine/sessionmaker
    _current_url = url
    eng = globals().get("_engine")
    if eng is not None:
        try:
            eng.dispose()
        except Exception:
            pass
    if url:
        # Normalize Windows SQLite file URLs and ensure parent directory exists
        if url.startswith("sqlite:///"):
            raw_path = url[len("sqlite:///"):]
            # Create parent directory best-effort
            try:
                dir_path = os.path.dirname(raw_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
            except Exception:
                pass
            # Normalize backslashes to forward slashes for sqlite URL
            if os.name == "nt" and "\\" in raw_path:
                url = "sqlite:///" + raw_path.replace("\\", "/")
        create_kwargs = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            # For SQLite in tests, avoid lingering locks on Windows and threads constraints
            create_kwargs["poolclass"] = NullPool
            create_kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_engine(url, **create_kwargs)
        globals()["_engine"] = engine
        globals()["_SessionLocal"] = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        # Best-effort auto-create schema for lightweight SQLite-based tests
        try:
            from app.db.models import Base  # local import to avoid cycles
            Base.metadata.create_all(engine)
        except Exception:
            # Non-fatal for environments where DDL isn't desired at init time
            pass
    else:
        globals()["_engine"] = None
        globals()["_SessionLocal"] = None


def get_engine():
    _configure_if_needed()
    return globals().get("_engine")


def db_enabled() -> bool:
    return get_engine() is not None and globals().get("_SessionLocal") is not None


def get_session() -> Session:
    if not db_enabled():
        raise RuntimeError("DB not enabled: DATABASE_URL is not set")
    return globals()["_SessionLocal"]()  # type: ignore[misc]


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    # Ensure engine/sessionmaker reflect current env each time
    _configure_if_needed()
    if not db_enabled():
        raise RuntimeError("DB not enabled: DATABASE_URL is not set")
    session = globals()["_SessionLocal"]()  # type: ignore[misc]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def __getattr__(name: str):
    """Dynamic access to module attributes for tests that read _engine/_SessionLocal."""
    if name == "_engine":
        return get_engine()
    if name == "_SessionLocal":
        _configure_if_needed()
        return globals().get("_SessionLocal")
    raise AttributeError(name)

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

_engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True) if DATABASE_URL else None
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True) if _engine else None


def db_enabled() -> bool:
    return _engine is not None and _SessionLocal is not None


def get_session() -> Session:
    if not db_enabled():
        raise RuntimeError("DB not enabled: DATABASE_URL is not set")
    return _SessionLocal()  # type: ignore[misc]


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    if not db_enabled():
        raise RuntimeError("DB not enabled: DATABASE_URL is not set")
    session = _SessionLocal()  # type: ignore[misc]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

def test_health_and_db_disabled(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.main import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    js = r.json()
    assert js.get("status") == "ok"
    assert "version" in js
    r2 = client.get("/health/db")
    assert r2.status_code == 200
    assert r2.json().get("enabled") is False


def test_health_db_enabled_and_request_headers(monkeypatch):
    # Setup temporary SQLite DB
    with tempfile.TemporaryDirectory() as td:
        db_url = f"sqlite:///{Path(td) / 'test.db'}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        from app.db import session as sess
        from app.db.models import Base
        eng = sess.get_engine()
        assert eng is not None
        Base.metadata.create_all(eng)
        from app.main import app
        client = TestClient(app)
        # health db
        r = client.get("/health/db")
        assert r.status_code == 200
        js = r.json()
        assert js.get("enabled") is True
        assert js.get("connection") == "ok"
        assert isinstance(js.get("ping_ms"), int)
        assert "version" in js
        # Logging/header echo: send IDs and expect echo back
        headers = {
            "X-Request-ID": "req-123",
            "X-Correlation-ID": "corr-xyz",
        }
        r2 = client.get("/health", headers=headers)
        assert r2.status_code == 200
        assert r2.headers.get("x-request-id") == "req-123"
        assert r2.headers.get("x-correlation-id") == "corr-xyz"

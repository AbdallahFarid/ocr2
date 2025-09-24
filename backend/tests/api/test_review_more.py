import io
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient


def test_get_item_404(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("AUDIT_ROOT", str(Path(td) / "audit"))
        from app.main import app
        client = TestClient(app)
        r = client.get("/review/items/QNB/NOFILE")
        assert r.status_code == 404


def test_upload_missing_params_returns_400(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("UPLOAD_DIR", str(Path(td) / "uploads"))
        monkeypatch.setenv("AUDIT_ROOT", str(Path(td) / "audit"))
        monkeypatch.setenv("BATCH_MAP_DIR", str(Path(td) / ".batch_map"))
        from app.main import app
        client = TestClient(app)
        r = client.post("/review/upload", data={"bank": "QNB"})
        assert r.status_code == 400
        assert "Provide a file" in r.text


essize = 1024 * 1024


def test_upload_too_large_returns_413(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("UPLOAD_DIR", str(Path(td) / "uploads"))
        monkeypatch.setenv("AUDIT_ROOT", str(Path(td) / "audit"))
        monkeypatch.setenv("BATCH_MAP_DIR", str(Path(td) / ".batch_map"))
        # set MAX_UPLOAD_MB to 0 to trigger immediate 413 on any content
        monkeypatch.setenv("MAX_UPLOAD_MB", "0")
        from app.main import app
        client = TestClient(app)
        files = {
            "file": ("big.jpg", b"X" * (1 * 1024), "image/jpeg"),
        }
        r = client.post("/review/upload", data={"bank": "QNB"}, files=files)
        assert r.status_code == 413
        assert "File too large" in r.text

import io
import os
import tempfile
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient


def setup_env(tmpdir: str, monkeypatch, with_db: bool = False):
    monkeypatch.setenv("UPLOAD_DIR", str(Path(tmpdir) / "uploads"))
    monkeypatch.setenv("AUDIT_ROOT", str(Path(tmpdir) / "audit"))
    monkeypatch.setenv("BATCH_MAP_DIR", str(Path(tmpdir) / ".batch_map"))
    if not with_db:
        monkeypatch.delenv("DATABASE_URL", raising=False)


def test_rate_limit_review_items(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        setup_env(td, monkeypatch, with_db=False)
        # Use runtime helper to avoid cross-test bucket contamination
        from app.main import app, set_rate_limit
        set_rate_limit(rps=0, burst=1, clear_buckets=True)
        client = TestClient(app)
        # first call passes
        r1 = client.get("/review/items")
        assert r1.status_code in (200, 204)
        # second call should be rate limited
        r2 = client.get("/review/items")
        assert r2.status_code == 429


def test_upload_sniff_single_invalid(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        setup_env(td, monkeypatch, with_db=False)
        monkeypatch.setenv("UPLOAD_SNIFF", "1")
        from app.main import app, set_rate_limit
        set_rate_limit(rps=1000, burst=1000, clear_buckets=True)
        client = TestClient(app)
        files = {
            "file": ("bad.jpg", b"not-an-image", "image/jpeg"),
        }
        r = client.post("/review/upload", data={"bank": "QNB"}, files=files)
        assert r.status_code == 400


def test_upload_sniff_zip_all_invalid(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        setup_env(td, monkeypatch, with_db=False)
        monkeypatch.setenv("UPLOAD_SNIFF", "1")
        from app.main import app, set_rate_limit
        set_rate_limit(rps=1000, burst=1000, clear_buckets=True)
        client = TestClient(app)
        # Build zip with a non-image masquerading as .jpg
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as zf:
            zf.writestr("fake.jpg", "hello")
        buf.seek(0)
        files = {
            "zip_file": ("z.zip", buf.read(), "application/zip"),
        }
        r = client.post("/review/upload", data={"bank": "QNB"}, files=files)
        assert r.status_code == 400


def test_zip_slip_prevent(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        setup_env(td, monkeypatch, with_db=False)
        from app.main import app
        client = TestClient(app)
        # Zip with path traversal - should be skipped → no valid images
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as zf:
            zf.writestr("../evil.jpg", "data")
        buf.seek(0)
        r = client.post(
            "/review/upload",
            data={"bank": "QNB"},
            files={"zip_file": ("z.zip", buf.read(), "application/zip")},
        )
        assert r.status_code == 400

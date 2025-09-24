from __future__ import annotations

import io
import json
import zipfile
from typing import Tuple, Dict, Any

from fastapi.testclient import TestClient

from app.main import app


def _make_zip_bytes(files: Dict[str, bytes]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return bio.getvalue()


def test_upload_zip_happy_path(monkeypatch):
    client = TestClient(app)

    # Monkeypatch pipeline to avoid heavy processing
    def fake_save_upload_and_process(**kwargs) -> Tuple[str, Dict[str, Any]]:
        orig_name = kwargs.get("original_filename", "file.jpg")
        file_id = orig_name.replace(".", "_")
        return file_id, {"imageUrl": f"/files/QNB/{file_id}"}

    import app.api.review as review_mod
    monkeypatch.setattr(review_mod, "save_upload_and_process", fake_save_upload_and_process)

    zbytes = _make_zip_bytes({
        "a.jpg": b"fake-jpeg-1",
        "b.png": b"fake-png-2",
        "subdir/c.tif": b"fake-tiff-3",
        "not-image.txt": b"ignore-me",
    })

    files = {
        "zip_file": ("QNB.zip", zbytes, "application/zip"),
    }
    resp = client.post("/review/upload", data={"bank": "QNB"}, files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 3  # three images, .txt ignored
    assert data["firstReviewUrl"].startswith("/review/QNB/")
    assert len(data["items"]) == 3


def test_upload_single_file(monkeypatch):
    client = TestClient(app)

    def fake_save_upload_and_process(**kwargs) -> Tuple[str, Dict[str, Any]]:
        return "file_id_1", {"imageUrl": "/files/QNB/file_id_1"}

    import app.api.review as review_mod
    monkeypatch.setattr(review_mod, "save_upload_and_process", fake_save_upload_and_process)

    files = {
        "file": ("x.jpg", b"fake", "image/jpeg"),
    }
    resp = client.post("/review/upload", data={"bank": "QNB"}, files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["bank"] == "QNB"
    assert data["file"] == "file_id_1"
    assert data["reviewUrl"] == "/review/QNB/file_id_1"

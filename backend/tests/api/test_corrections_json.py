from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any

from fastapi.testclient import TestClient

from app.main import app


def _write_audit_json(root: Path, bank: str, file_id: str, fields: Dict[str, Dict[str, Any]]):
    bank_dir = root / bank
    bank_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": "2025-09-23T12:00:00Z",
        "correlation_id": None,
        "bank": bank,
        "file": file_id,
        "source_csv": None,
        "decision": {
            "decision": "review",
            "stp": False,
            "overall_conf": 0.5,
            "low_conf_fields": [],
            "reasons": [],
        },
        "fields": fields,
        "meta": {},
    }
    with open(bank_dir / f"{file_id}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def test_submit_corrections_updates_json(tmp_path, monkeypatch):
    # Point audit root to temp
    monkeypatch.setenv("AUDIT_ROOT", str(tmp_path))
    client = TestClient(app)

    # Seed an audit JSON
    fields = {
        "cheque_number": {"parse_norm": "12345", "ocr_text": "12345", "ocr_lang": "en"},
        "amount_numeric": {"parse_norm": "100.00", "ocr_text": "100.00", "ocr_lang": "en"},
    }
    _write_audit_json(tmp_path, "QNB", "F1", fields)

    # Submit a correction
    payload = {
        "reviewer_id": "user1",
        "updates": {
            "cheque_number": {"value": "12346", "reason": "typo"},
        },
        "correlation_id": None,
    }
    resp = client.post("/review/items/QNB/F1/corrections", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert "cheque_number" in data["updated_fields"]

    # Verify file updated
    with open(tmp_path / "QNB" / "F1.json", "r", encoding="utf-8") as f:
        updated = json.load(f)
    assert updated["fields"]["cheque_number"]["parse_norm"] == "12346"
    assert isinstance(updated.get("corrections"), list) and len(updated["corrections"]) >= 1

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def _write_audit(root: Path, bank: str, file_id: str, fields: dict):
    bank_dir = root / bank
    bank_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": "2025-09-23T12:00:00+00:00",
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


def test_export_csv_contains_bom_and_expected_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_ROOT", str(tmp_path))
    client = TestClient(app)

    _write_audit(tmp_path, "QNB", "F1", {
        "date": {"parse_norm": "2025-09-23"},
        "cheque_number": {"parse_norm": "1234567890"},
        "amount_numeric": {"parse_norm": "100.50"},
    })
    _write_audit(tmp_path, "QNB", "F2", {
        "date": {"parse_norm": "2025-09-24"},
        "cheque_number": {"parse_norm": "1234567891"},
        "amount_numeric": {"parse_norm": "200.00"},
    })

    payload = {
        "items": [
            {"bank": "QNB", "file": "F1"},
            {"bank": "QNB", "file": "F2"},
        ],
        "overrides": None,
        "format": "csv",
    }
    resp = client.post("/review/export", json=payload)
    assert resp.status_code == 200, resp.text
    text = resp.text
    # Must start with BOM
    assert text.startswith("\ufeff"), "CSV must start with UTF-8 BOM"
    # Header row
    assert "Bank,date,cheque number,amount" in text.splitlines()[0]
    # Rows contain our values
    assert any(
        line.startswith("QNB,2025-09-23,1234567890,100.50")
        for line in text.splitlines()
    )
    assert any(
        line.startswith("QNB,2025-09-24,1234567891,200.00")
        for line in text.splitlines()
    )

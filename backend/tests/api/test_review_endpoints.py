from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.main import app


def _write_audit(root: Path, bank: str, file_id: str) -> str:
    bank_dir = root / bank
    bank_dir.mkdir(parents=True, exist_ok=True)
    p = bank_dir / f"{file_id}.json"
    payload = {
        "schema_version": 1,
        "generated_at": "2025-01-01T00:00:00Z",
        "correlation_id": None,
        "bank": bank,
        "file": file_id,
        "source_csv": None,
        "decision": {
            "decision": "review",
            "stp": False,
            "overall_conf": 0.9,
            "low_conf_fields": ["date"],
            "reasons": ["low_confidence:date:0.90<thr0.995"],
        },
        "fields": {
            "date": {
                "field_conf": 0.99,
                "loc_conf": 1.0,
                "ocr_conf": 0.99,
                "validation": {"ok": True, "code": "OK"},
                "parse_ok": True,
                "parse_norm": "2025-01-01",
                "ocr_text": "01/Jan/2025",
                "ocr_lang": "en",
                "meets_threshold": False,
            },
            "amount_numeric": {
                "field_conf": 1.0,
                "loc_conf": 1.0,
                "ocr_conf": 1.0,
                "validation": {"ok": True, "code": "OK"},
                "parse_ok": True,
                "parse_norm": "100.00",
                "ocr_text": "100.00",
                "ocr_lang": "en",
                "meets_threshold": True,
            },
        },
        "meta": {},
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_list_get_and_corrections_roundtrip(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setenv("AUDIT_ROOT", str(root))
        _write_audit(root, "FABMISR", "TEST-1")

        client = TestClient(app)

        # List items
        r = client.get("/review/items")
        assert r.status_code == 200
        data = r.json()
        assert any(item["bank"] == "FABMISR" and item["file"] == "TEST-1" for item in data)

        # Get single item
        r2 = client.get("/review/items/FABMISR/TEST-1")
        assert r2.status_code == 200
        item = r2.json()
        assert item["bank"] == "FABMISR"
        assert item["file"] == "TEST-1"
        assert item["fields"]["date"]["parse_norm"] == "2025-01-01"

        # Post corrections
        payload = {
            "reviewer_id": "tester",
            "updates": {
                "date": {"value": "2025-01-02", "reason": "typo"}
            }
        }
        r3 = client.post("/review/items/FABMISR/TEST-1/corrections", json=payload)
        assert r3.status_code == 200
        out = r3.json()
        assert out["ok"] is True
        assert "date" in out["updated_fields"]

        # Verify audit file updated
        audit_path = root / "FABMISR" / "TEST-1.json"
        updated = json.loads(audit_path.read_text(encoding="utf-8"))
        assert updated["fields"]["date"]["parse_norm"] == "2025-01-02"
        assert isinstance(updated.get("corrections"), list)
        assert any(c.get("field") == "date" and c.get("after") == "2025-01-02" for c in updated["corrections"])

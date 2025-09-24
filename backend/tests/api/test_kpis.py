from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def _write_audit(root: Path, bank: str, file_id: str, fields: dict, corrections: list[dict] | None = None, ts: str | None = None):
    bank_dir = root / bank
    bank_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": ts or datetime.now(timezone.utc).isoformat(),
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
        "corrections": corrections or [],
        "meta": {},
    }
    with open(bank_dir / f"{file_id}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def test_kpi_per_bank_excludes_name_and_respects_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_ROOT", str(tmp_path))
    client = TestClient(app)

    # Two files for QNB; only one has corrections on non-name field
    _write_audit(
        tmp_path,
        "QNB",
        "A1",
        fields={"name": {"parse_norm": "X"}, "amount_numeric": {"parse_norm": "100"}},
        corrections=[{"field": "name"}],  # should be excluded
        ts="2025-09-23T10:00:00+00:00",
    )
    _write_audit(
        tmp_path,
        "QNB",
        "A2",
        fields={"amount_numeric": {"parse_norm": ""}, "date": {"parse_norm": "2025-09-23"}},
        corrections=[{"field": "amount_numeric"}],  # counts as error
        ts="2025-09-23T11:00:00+00:00",
    )

    # One file for CIB, out of range by date
    _write_audit(
        tmp_path,
        "CIB",
        "C1",
        fields={"amount_numeric": {"parse_norm": "200"}},
        corrections=[],
        ts="2025-09-22T23:00:00+00:00",
    )

    resp = client.get("/metrics/kpi/per-bank", params={"from": "2025-09-23T00:00:00Z", "to": "2025-09-23T23:59:59Z"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Only QNB records should be counted for that date range
    assert "QNB" in data
    q = data["QNB"]
    assert q["total_cheques"] == 2
    assert q["cheques_with_errors"] == 1  # only A2
    assert q["total_fields"] >= 2  # at least fields counted excluding 'name'

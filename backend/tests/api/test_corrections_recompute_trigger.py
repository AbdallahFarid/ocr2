import json
import tempfile
from pathlib import Path
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient


def setup_sqlite(monkeypatch):
    td = tempfile.TemporaryDirectory()
    db_url = f"sqlite:///{Path(td.name) / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    audit_root = Path(td.name) / "audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AUDIT_ROOT", str(audit_root))
    monkeypatch.setenv("BATCH_MAP_DIR", str(Path(td.name) / '.batch_map'))
    from app.db import session as sess
    from app.db.models import Base
    eng = sess.get_engine()
    assert eng is not None
    Base.metadata.create_all(eng)
    return td, audit_root


def write_audit(audit_root: Path, bank: str, file_id: str, fields: dict):
    bank_dir = audit_root / bank
    bank_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "correlation_id": None,
        "bank": bank,
        "file": file_id,
        "source_csv": None,
        "decision": {"decision": "review", "stp": False, "overall_conf": 0.9, "low_conf_fields": [], "reasons": []},
        "fields": fields,
        "corrections": [],
        "meta": {},
    }
    with open(bank_dir / f"{file_id}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def test_corrections_triggers_recompute(monkeypatch):
    td, audit_root = setup_sqlite(monkeypatch)
    try:
        from app.main import app
        from app.db import session as sess
        from app.db import crud as dbcrud
        from app.db.models import Base

        # DB seed: bank, batch, cheque with fields
        with sess.session_scope() as db:
            dbcrud.ensure_bank_exists(db, code="NBE", name="NBE")
            b = dbcrud.create_batch(db, bank_code="NBE", name="01_01_2025_NBE_01", batch_date=date(2025, 1, 1), seq=1)
            dbcrud.create_cheque_with_fields(
                db,
                batch=b,
                bank_code="NBE",
                file_id="F123",
                original_filename="F123.jpg",
                image_path=None,
                decision={"decision": "review", "stp": False, "overall_conf": 0.9},
                processed_at=datetime.now(timezone.utc),
                index_in_batch=0,
                fields={"date": {"meets_threshold": False}, "cheque_number": {"meets_threshold": False}, "amount_numeric": {"meets_threshold": False}},
            )
        # Audit JSON for the same cheque
        write_audit(audit_root, "NBE", "F123", fields={"date": {"parse_norm": "2025-01-01"}})

        # Monkeypatch background recompute
        called = {"ok": False, "args": None}
        import app.api.review as review_mod

        def fake_bg(bank_code: str, batch_name: str):
            called["ok"] = True
            called["args"] = (bank_code, batch_name)

        monkeypatch.setattr(review_mod, "_bg_recompute_kpis", fake_bg)

        client = TestClient(app)
        body = {
            "reviewer_id": "test",
            "updates": {"date": {"value": "2025-01-02", "reason": "fix"}},
        }
        r = client.post("/review/items/NBE/F123/corrections", json=body)
        assert r.status_code == 200, r.text
        assert called["ok"] is True
        assert called["args"][0] == "NBE"
    finally:
        td.cleanup()

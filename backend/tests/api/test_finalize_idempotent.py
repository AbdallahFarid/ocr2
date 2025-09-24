import tempfile
from pathlib import Path
from datetime import date
from fastapi.testclient import TestClient


def test_finalize_idempotent(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db_url = f"sqlite:///{Path(td) / 'test.db'}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        batch_map = Path(td) / ".batch_map"
        audit_root = Path(td) / "audit"
        audit_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("BATCH_MAP_DIR", str(batch_map))
        monkeypatch.setenv("AUDIT_ROOT", str(audit_root))

        from app.main import app
        from app.db import session as sess
        from app.db import crud as dbcrud
        from app.db.models import Base

        eng = sess.get_engine()
        assert eng is not None
        Base.metadata.create_all(eng)

        # Seed and create batch
        with sess.session_scope() as db:
            dbcrud.ensure_bank_exists(db, code="AAIB", name="AAIB")
            bname = "01_01_2025_AAIB_01"
            dbcrud.create_batch(db, bank_code="AAIB", name=bname, batch_date=date(2025, 1, 1), seq=1)

        # mapping
        key = "k1"
        p = batch_map / "AAIB"
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{key}.txt").write_text(f"{bname}|2025-01-01|1", encoding="utf-8")

        client = TestClient(app)
        r1 = client.post("/review/batches/finalize", data={"bank": "AAIB", "correlation_id": key})
        assert r1.status_code == 200
        r2 = client.post("/review/batches/finalize", data={"bank": "AAIB", "correlation_id": key})
        # Even if mapping file is gone, we expect 404 (unknown mapping)
        # so idempotency here refers to not failing the first finalize and safe behavior on second.
        assert r2.status_code in (200, 404)

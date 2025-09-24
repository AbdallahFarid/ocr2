import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient


def test_finalize_requires_db(monkeypatch):
    # Ensure DB is disabled
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Map dir points to temp
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("BATCH_MAP_DIR", td)
        # Import app after env setup
        from app.main import app
        client = TestClient(app)
        # No mapping file -> 404 first
        r = client.post("/review/batches/finalize", data={"bank": "FABMISR", "correlation_id": "q1"})
        assert r.status_code == 404
        # Create a dummy mapping file, still DB disabled -> 503
        bank_dir = Path(td) / "FABMISR"
        bank_dir.mkdir(parents=True, exist_ok=True)
        (bank_dir / "q1.txt").write_text("24_09_2025_FABMISR_1|2025-09-24|1", encoding="utf-8")
        r2 = client.post("/review/batches/finalize", data={"bank": "FABMISR", "correlation_id": "q1"})
        assert r2.status_code == 503


def test_finalize_happy_path_sqlite(monkeypatch):
    # Configure a temporary SQLite DB
    with tempfile.TemporaryDirectory() as td:
        db_url = f"sqlite:///{Path(td) / 'test.db'}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        # BATCH_MAP_DIR and AUDIT_ROOT
        batch_map = Path(td) / ".batch_map"
        audit_root = Path(td) / "audit"
        audit_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("BATCH_MAP_DIR", str(batch_map))
        monkeypatch.setenv("AUDIT_ROOT", str(audit_root))

        # Import after env setup so engine initializes correctly
        from app.main import app
        from app.db import session as sess
        from app.db import crud as dbcrud
        from app.db.models import Base

        # Create schema via initialized engine
        eng = sess.get_engine()
        assert eng is not None
        Base.metadata.create_all(eng)

        # Seed bank and create batch that matches mapping name
        from datetime import date
        import random
        with sess.session_scope() as db:
            dbcrud.ensure_bank_exists(db, code="FABMISR", name="FABMISR")
            # Use a unique seq to avoid collisions with any existing rows in a shared DB
            seq = random.randint(1000, 9999)
            batch_name = f"24_09_2025_FABMISR_{seq}"
            dbcrud.create_batch(db, bank_code="FABMISR", name=batch_name, batch_date=date(2025, 9, 24), seq=seq)

        # Create correlation mapping file
        key = "q2"
        p = batch_map / "FABMISR"
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{key}.txt").write_text(f"{batch_name}|2025-09-24|{seq}", encoding="utf-8")

        client = TestClient(app)
        r = client.post("/review/batches/finalize", data={"bank": "FABMISR", "correlation_id": key})
        assert r.status_code == 200, r.text
        js = r.json()
        assert js["ok"] is True
        assert js["batch"] == batch_name
        # Mapping file should be removed best-effort
        assert not (p / f"{key}.txt").exists()

        # Verify processing_ended_at set
        from app.db.models import Batch
        with sess.session_scope() as db:
            b = db.query(Batch).filter(Batch.name == batch_name, Batch.bank_code == "FABMISR").first()
            assert b is not None
            assert b.processing_ended_at is not None

import json
import tempfile
from pathlib import Path
from datetime import date, datetime, timezone

from app.services.upload import save_upload_and_process


def _fake_fields():
    # Minimal fields map with required keys and high conf to simplify assertions
    return {
        "date": {"field_conf": 1.0, "parse_norm": "2025-01-01", "meets_threshold": True},
        "cheque_number": {"field_conf": 1.0, "parse_norm": "123", "meets_threshold": True},
        "amount_numeric": {"field_conf": 1.0, "parse_norm": "100.00", "meets_threshold": True},
        "name": {"field_conf": 1.0, "parse_norm": "John Doe", "meets_threshold": True},
    }


def test_save_upload_and_process_without_db(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        upload_dir = Path(td) / "uploads"
        audit_root = Path(td) / "audit"
        upload_dir.mkdir(parents=True, exist_ok=True)
        audit_root.mkdir(parents=True, exist_ok=True)
        bank = "QNB"
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Fake pipeline returns deterministic fields
        import app.services.upload as upload_mod
        monkeypatch.setattr(upload_mod, "run_pipeline_on_image", lambda *args, **kwargs: _fake_fields())
        file_id, item = save_upload_and_process(
            upload_dir=str(upload_dir),
            audit_root=str(audit_root),
            bank=bank,
            file_bytes=b"test-bytes",
            original_filename="x.jpg",
            correlation_id=None,
            public_base="http://test",
            db_batch_name=None,
            index_in_batch=0,
        )
        # File is saved
        assert (upload_dir / bank / file_id).exists()
        # Audit JSON written
        p = audit_root / bank / f"{Path(file_id).name}.json"
        assert p.exists()
        js = json.loads(p.read_text(encoding="utf-8"))
        assert js["bank"] == bank
        assert js["file"] == Path(file_id).name
        assert "fields" in js and "decision" in js
        # Response contains imageUrl
        assert item["imageUrl"].endswith(f"/files/{bank}/{Path(file_id).name}")


def test_save_upload_and_process_with_db(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        upload_dir = Path(td) / "uploads"
        audit_root = Path(td) / "audit"
        upload_dir.mkdir(parents=True, exist_ok=True)
        audit_root.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{Path(td) / 'test.db'}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        # Prepare DB schema
        from app.db import session as sess
        from app.db.models import Base, Batch, Cheque
        eng = sess.get_engine()
        assert eng is not None
        Base.metadata.create_all(eng)
        bank = "AAIB"
        # Fake pipeline returns deterministic fields
        import app.services.upload as upload_mod
        monkeypatch.setattr(upload_mod, "run_pipeline_on_image", lambda *args, **kwargs: _fake_fields())
        file_id, item = save_upload_and_process(
            upload_dir=str(upload_dir),
            audit_root=str(audit_root),
            bank=bank,
            file_bytes=b"test-bytes",
            original_filename="y.png",
            correlation_id="corr1",
            public_base="http://test",
            db_batch_name="01_01_2025_AAIB_01",
            db_batch_date=date(2025, 1, 1),
            db_seq=1,
            index_in_batch=1,
        )
        # DB rows created
        from app.db import crud as dbcrud
        with sess.session_scope() as db:
            b = dbcrud.get_batch_by_name(db, bank_code=bank, name="01_01_2025_AAIB_01")
            assert b is not None
            # Cheque exists
            ch = db.query(Cheque).filter(Cheque.batch_id == b.id, Cheque.file_id == Path(file_id).name).first()
            assert ch is not None

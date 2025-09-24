import tempfile
from pathlib import Path
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient


def setup_sqlite(monkeypatch):
    td = tempfile.TemporaryDirectory()
    db_url = f"sqlite:///{Path(td.name) / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("AUDIT_ROOT", str(Path(td.name) / 'audit'))
    monkeypatch.setenv("BATCH_MAP_DIR", str(Path(td.name) / '.batch_map'))
    from app.db import session as sess
    from app.db.models import Base
    eng = sess.get_engine()
    assert eng is not None
    Base.metadata.create_all(eng)
    return td


def test_recompute_kpis_and_flagging(monkeypatch):
    td = setup_sqlite(monkeypatch)
    try:
        from app.db import session as sess
        from app.db import crud as dbcrud
        from app.db.models import Batch

        with sess.session_scope() as db:
            dbcrud.ensure_bank_exists(db, code="CIB", name="CIB")
            b = dbcrud.create_batch(db, bank_code="CIB", name="01_01_2025_CIB_01", batch_date=date(2025, 1, 1), seq=1)
            # Create 5 cheques. KPIs are based on edits (corrections), not confidence.
            # We'll apply corrections to the first 4 cheques only → 4/5 = 0.8 (not flagged since threshold is > 0.8)
            for i in range(5):
                c = dbcrud.create_cheque_with_fields(
                    db,
                    batch=b,
                    bank_code="CIB",
                    file_id=f"f{i}",
                    original_filename=f"f{i}.jpg",
                    image_path=None,
                    decision={"decision": "review", "stp": False, "overall_conf": 0.9},
                    processed_at=datetime.now(timezone.utc),
                    index_in_batch=i,
                    fields={
                        # Initial meets_threshold values are informational only; KPIs depend on corrections
                        "date": {"meets_threshold": True, "parse_norm": "2025-01-01"},
                        "cheque_number": {"meets_threshold": True, "parse_norm": "123"},
                        "amount_numeric": {"meets_threshold": True, "parse_norm": "100.00"},
                        "name": {"meets_threshold": True, "parse_norm": "X"},
                    },
                )
                # Apply a correction to KPI field 'date' for first 4 cheques only
                if i < 4:
                    dbcrud.apply_corrections(
                        db,
                        bank_code="CIB",
                        file_id=f"f{i}",
                        corrections={"date": {"before": "2025-01-01", "after": "2025-01-02", "reason": None}},
                        reviewer_id="test",
                        at=datetime.now(timezone.utc),
                    )
            metrics = dbcrud.recompute_and_update_batch_kpis_by_name(db, bank_code="CIB", batch_name=b.name)
            assert metrics is not None
        # Reload and assert not flagged at 0.8
        with sess.session_scope() as db:
            bb = db.query(Batch).filter(Batch.name == "01_01_2025_CIB_01").first()
            assert bb is not None
            assert bb.error_rate_cheques is not None
            assert float(bb.error_rate_cheques) == 0.8
            assert bb.flagged is False
        # Now make the last cheque incorrect via a correction to push > 0.8
        with sess.session_scope() as db:
            b = db.query(Batch).filter(Batch.name == "01_01_2025_CIB_01").first()
            assert b is not None
            # Apply a correction for the last cheque 'f4'
            dbcrud.apply_corrections(
                db,
                bank_code="CIB",
                file_id="f4",
                corrections={"date": {"before": "2025-01-01", "after": "2025-01-03", "reason": None}},
                reviewer_id="test",
                at=datetime.now(timezone.utc),
            )
            m2 = dbcrud.recompute_and_update_batch_kpis_by_name(db, bank_code="CIB", batch_name=b.name)
            assert m2 is not None
        with sess.session_scope() as db:
            bb = db.query(Batch).filter(Batch.name == "01_01_2025_CIB_01").first()
            assert bb is not None
            assert float(bb.error_rate_cheques) == 1.0
            assert bb.flagged is True
    finally:
        td.cleanup()

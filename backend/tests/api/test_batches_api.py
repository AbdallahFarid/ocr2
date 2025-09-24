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


def test_list_batches_and_detail(monkeypatch):
    td = setup_sqlite(monkeypatch)
    try:
        from app.main import app
        from app.db import session as sess
        from app.db import crud as dbcrud

        # Seed bank and batch
        with sess.session_scope() as db:
            dbcrud.ensure_bank_exists(db, code="QNB", name="QNB")
            b = dbcrud.create_batch(db, bank_code="QNB", name="01_01_2025_QNB_01", batch_date=date(2025, 1, 1), seq=1)
            # Add one cheque
            dbcrud.create_cheque_with_fields(
                db,
                batch=b,
                bank_code="QNB",
                file_id="f1",
                original_filename="f1.jpg",
                image_path=None,
                decision={"decision": "review", "stp": False, "overall_conf": 0.9},
                processed_at=datetime.now(timezone.utc),
                index_in_batch=0,
                fields={}
            )

        client = TestClient(app)

        # List
        r = client.get("/batches", params={"bank": "QNB"})
        assert r.status_code == 200, r.text
        lst = r.json()
        assert isinstance(lst, list)
        assert any(x["name"] == "01_01_2025_QNB_01" for x in lst)

        # Detail
        r2 = client.get("/batches/QNB/01_01_2025_QNB_01")
        assert r2.status_code == 200, r2.text
        js = r2.json()
        assert js["bank"] == "QNB"
        assert js["name"] == "01_01_2025_QNB_01"
        assert isinstance(js.get("cheques"), list)
        assert any(c["file"] == "f1" for c in js["cheques"])
    finally:
        td.cleanup()

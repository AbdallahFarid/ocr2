from fastapi.testclient import TestClient

def test_batches_requires_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.main import app
    client = TestClient(app)
    r = client.get("/batches", params={"bank": "QNB"})
    assert r.status_code == 503


def test_batch_detail_requires_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.main import app
    client = TestClient(app)
    r = client.get("/batches/QNB/01_01_2025_QNB_01")
    assert r.status_code == 503

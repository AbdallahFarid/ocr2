import pytest

from app.pipeline.postprocess import parse_and_normalize


def test_parse_and_normalize_date():
    r = parse_and_normalize("date", "31/Dec/25")
    assert r["parse_ok"] is True
    assert r["norm"] == "2025-12-31"


def test_parse_and_normalize_amount():
    r = parse_and_normalize("amount_numeric", "21,116.00")
    assert r["parse_ok"] is True
    assert r["norm"] == "21116.00"


def test_parse_and_normalize_cheque_number():
    r = parse_and_normalize("cheque_number", "No : 11637510")
    assert r["parse_ok"] is True
    assert r["norm"] == "11637510"


def test_parse_and_normalize_name_arabic():
    r = parse_and_normalize("name", " ةــكــرش بالم هيلز للتعمير  ")
    assert r["parse_ok"] is True
    assert isinstance(r["norm"], str) and len(r["norm"]) >= 3

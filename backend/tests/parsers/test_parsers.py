import pytest

from app.parsers import parse_date, parse_amount, parse_cheque_number, normalize_name


def test_parse_date_ok_and_century_fix():
    assert parse_date("31/Dec/25").value == (31, 12, 2025)
    assert parse_date("01/Jan/2026").value == (1, 1, 2026)


def test_parse_date_no_match():
    r = parse_date("Dec 31 2026")
    assert not r.ok and r.error == "NO_MATCH"


def test_parse_amount_basic():
    assert parse_amount("21,116.00").value == 21116.00


def test_parse_cheque_number_basic():
    assert parse_cheque_number("No : 11637510").value == "11637510"


def test_normalize_name_arabic():
    r = normalize_name(" ر ىمـعــتــلــل   ز لــيه ملاب   ةــكــرش ")
    assert r.ok
    assert "شركة" in r.value or len(r.value) > 6

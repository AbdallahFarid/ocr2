import pytest

from app.validations import (
    ErrorCode,
    validate_date,
    validate_amount,
    validate_cheque_number,
    validate_payee,
    validate_currency,
)


def test_validate_date_ok_and_bounds():
    r = validate_date((31, 12, 2025))
    assert r.ok and r.code == ErrorCode.OK
    r2 = validate_date("2026-01-01")
    assert r2.ok and r2.code == ErrorCode.OK
    r3 = validate_date((1, 1, 1999))
    assert not r3.ok and r3.code == ErrorCode.DATE_RANGE


def test_validate_amount_ok_and_errors():
    assert validate_amount(1.0).ok
    assert not validate_amount(0.0).ok
    assert validate_amount("21116.00").ok
    bad = validate_amount("abc")
    assert not bad.ok and bad.code in (ErrorCode.AMOUNT_RANGE,)


def test_validate_cheque_number_length_and_digits():
    ok = validate_cheque_number("No : 11637510")
    assert ok.ok and ok.code == ErrorCode.OK
    short = validate_cheque_number("123")
    assert not short.ok and short.code == ErrorCode.CHEQUE_PATTERN


def test_validate_payee_master_threshold():
    master = [
        "شركة بالم زليه للتعمير",
        "شركة عينة للاختبار",
    ]
    ok = validate_payee("شركة عينة للاختبار", master=master, threshold=0.8)
    assert ok.ok and ok.code == ErrorCode.OK
    miss = validate_payee("شركة مختلفة تماما", master=master, threshold=0.95)
    assert not miss.ok and miss.code == ErrorCode.PAYEE_NOT_IN_MASTER


def test_validate_currency_allowed():
    assert validate_currency("EGP").ok
    assert not validate_currency("XYZ").ok


def test_validate_cheque_number_bank_specific_patterns():
    # QNB pattern allows 8-12 digits in our baseline
    ok_qnb = validate_cheque_number("No: 12345678", bank_id="QNB")
    assert ok_qnb.ok
    bad_qnb = validate_cheque_number("1133011199540801012", bank_id="QNB")
    assert not bad_qnb.ok

    # FABMISR similar baseline 8-12 digits
    ok_fab = validate_cheque_number("000012345678", bank_id="FABMISR")
    assert ok_fab.ok
    bad_fab = validate_cheque_number("12345", bank_id="FABMISR")
    assert not bad_fab.ok

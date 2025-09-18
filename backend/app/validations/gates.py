from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import difflib

from .error_codes import ErrorCode
from .patterns import CHEQUE_NUMBER_PATTERNS


@dataclass
class ValidationResult:
    ok: bool
    code: ErrorCode
    meta: Dict[str, Any]


def _parse_date_input(value: Union[str, Tuple[int, int, int]]) -> Optional[Tuple[int, int, int]]:
    if isinstance(value, tuple) and len(value) == 3:
        d, m, y = value
        return int(d), int(m), int(y)
    if isinstance(value, str):
        # Expect YYYY-MM-DD
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
        if not m:
            return None
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (d, mo, y)
    return None


def validate_date(value: Union[str, Tuple[int, int, int]], *, min_year: int = 2000, max_year: int = 2100) -> ValidationResult:
    if value in (None, ""):
        return ValidationResult(False, ErrorCode.DATE_EMPTY, {"value": value})
    parsed = _parse_date_input(value)
    if not parsed:
        return ValidationResult(False, ErrorCode.DATE_INVALID, {"value": value})
    d, m, y = parsed
    if not (min_year <= y <= max_year):
        return ValidationResult(False, ErrorCode.DATE_RANGE, {"y": y, "min": min_year, "max": max_year})
    try:
        date(y, m, d)
    except Exception as e:
        return ValidationResult(False, ErrorCode.DATE_INVALID, {"error": str(e), "d": d, "m": m, "y": y})
    return ValidationResult(True, ErrorCode.OK, {"d": d, "m": m, "y": y})


def validate_amount(value: Optional[Union[str, float, int]], *, min_amount: float = 0.01, max_amount: float = 1_000_000_000.0) -> ValidationResult:
    if value in (None, ""):
        return ValidationResult(False, ErrorCode.AMOUNT_EMPTY, {"value": value})
    try:
        amt = float(value)
    except Exception:
        return ValidationResult(False, ErrorCode.AMOUNT_RANGE, {"value": value})
    if amt <= 0:
        return ValidationResult(False, ErrorCode.AMOUNT_NONPOS, {"amount": amt})
    if not (min_amount <= amt <= max_amount):
        return ValidationResult(False, ErrorCode.AMOUNT_RANGE, {"amount": amt, "min": min_amount, "max": max_amount})
    return ValidationResult(True, ErrorCode.OK, {"amount": amt})


def validate_cheque_number(value: Optional[str], *, bank_id: Optional[str] = None, length_range: Tuple[int, int] = (6, 16)) -> ValidationResult:
    if value in (None, ""):
        return ValidationResult(False, ErrorCode.CHEQUE_EMPTY, {})
    s = re.sub(r"\D+", "", str(value))
    # Prefer bank-specific patterns when available
    if bank_id:
        pat = CHEQUE_NUMBER_PATTERNS.get(str(bank_id))
        if pat and pat.get("regex"):
            rx = re.compile(str(pat["regex"]))
            if not rx.match(s):
                return ValidationResult(
                    False,
                    ErrorCode.CHEQUE_PATTERN,
                    {"digits": s, "len": len(s), "regex": pat["regex"], "bank": bank_id},
                )
            return ValidationResult(True, ErrorCode.OK, {"digits": s, "bank": bank_id})
    # Fallback generic length check
    min_len, max_len = length_range
    if not (min_len <= len(s) <= max_len):
        return ValidationResult(False, ErrorCode.CHEQUE_PATTERN, {"digits": s, "len": len(s), "range": length_range, "bank": bank_id})
    return ValidationResult(True, ErrorCode.OK, {"digits": s, "bank": bank_id})


def validate_payee(name: Optional[str], *, master: Optional[Sequence[str]] = None, threshold: float = 0.85) -> ValidationResult:
    if name is None:
        return ValidationResult(False, ErrorCode.PAYEE_EMPTY, {})
    s = str(name).strip()
    # Normalize spaces
    s = re.sub(r"\s+", " ", s)
    if len(s) < 3:
        return ValidationResult(False, ErrorCode.PAYEE_TOO_SHORT, {"name": s})
    if not master:
        return ValidationResult(True, ErrorCode.OK, {"name": s})
    # Use difflib similarity ratio (language-agnostic)
    best_ratio = 0.0
    best_match = None
    for cand in master:
        r = difflib.SequenceMatcher(None, s, str(cand)).ratio()
        if r > best_ratio:
            best_ratio = r
            best_match = cand
    if best_ratio >= threshold:
        return ValidationResult(True, ErrorCode.OK, {"name": s, "match": best_match, "ratio": best_ratio})
    return ValidationResult(False, ErrorCode.PAYEE_NOT_IN_MASTER, {"name": s, "best": best_match, "ratio": best_ratio, "threshold": threshold})


def validate_currency(currency: Optional[str], *, allowed: Sequence[str] = ("EGP", "USD", "EUR", "AED", "SAR")) -> ValidationResult:
    if not currency:
        return ValidationResult(False, ErrorCode.CURRENCY_INVALID, {"currency": currency, "allowed": list(allowed)})
    c = str(currency).upper().strip()
    if c not in set(allowed):
        return ValidationResult(False, ErrorCode.CURRENCY_INVALID, {"currency": c, "allowed": list(allowed)})
    return ValidationResult(True, ErrorCode.OK, {"currency": c})

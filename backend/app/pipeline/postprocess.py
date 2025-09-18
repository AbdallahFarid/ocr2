from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.parsers import parse_date, parse_amount, parse_cheque_number, normalize_name


def parse_and_normalize(field: str, text: str) -> Dict[str, Any]:
    """Parse and normalize OCR text for a known field.

    Returns a dict with: { norm: Optional[str], parse_ok: bool, parse_err: Optional[str] }
    - For date: norm = YYYY-MM-DD
    - For amount_numeric: norm = decimal string with 2 dp
    - For cheque_number: norm = digits only
    - For name: norm = normalized name (Arabic-safe)
    Other fields return empty normalization.
    """
    if not text:
        return {"norm": None, "parse_ok": False, "parse_err": "EMPTY"}

    if field == "date":
        r = parse_date(text)
        if r.ok and r.value:
            d, m, y = r.value
            return {"norm": f"{y:04d}-{m:02d}-{d:02d}", "parse_ok": True, "parse_err": None}
        return {"norm": None, "parse_ok": False, "parse_err": r.error}

    if field == "amount_numeric":
        r = parse_amount(text)
        if r.ok and r.value is not None:
            return {"norm": f"{float(r.value):.2f}", "parse_ok": True, "parse_err": None}
        return {"norm": None, "parse_ok": False, "parse_err": r.error}

    if field == "cheque_number":
        r = parse_cheque_number(text)
        if r.ok and r.value:
            return {"norm": str(r.value), "parse_ok": True, "parse_err": None}
        return {"norm": None, "parse_ok": False, "parse_err": r.error}

    if field == "name":
        r = normalize_name(text)
        if r.ok and r.value:
            return {"norm": str(r.value), "parse_ok": True, "parse_err": None}
        return {"norm": None, "parse_ok": False, "parse_err": r.error}

    return {"norm": None, "parse_ok": False, "parse_err": None}

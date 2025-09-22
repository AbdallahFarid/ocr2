from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple, Any, Dict

from app.ocr.text_utils import normalize_digits, fix_arabic_text


@dataclass
class ParseResult:
    value: Any
    ok: bool
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


_DATE_RX = re.compile(r"(?i)\b(\d{1,2})\s*[\-/\.]\s*([A-Za-z0-9]{3})\s*[\-/\.]\s*(\d{2,4})\b")
_AMOUNT_RX = re.compile(r"\b\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})?\b")
_CHEQUE_RX = re.compile(r"\b\d{6,}\b")

_MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
    # OCR-tolerant aliases
    "0CT": 10,
    "0EC": 12,
    "N0V": 11,
}


def parse_date(text: str) -> ParseResult:
    if not text:
        return ParseResult(value=None, ok=False, error="EMPTY")
    s = normalize_digits(text)
    m = _DATE_RX.search(s)
    if not m:
        return ParseResult(value=None, ok=False, error="NO_MATCH", meta={"text": text})
    day, mon, yr = m.group(1), m.group(2), m.group(3)
    mon_u = mon.upper().strip()
    # Try multiple OCR fixups: zero can be mistaken for 'O' (Oct) or 'D' (Dec)
    aliases = [mon_u, mon_u.replace('0', 'O'), mon_u.replace('0', 'D')]
    year = int(yr)
    if year < 100:
        year += 2000
    month = None
    for key in aliases:
        if key in _MONTH_MAP:
            month = _MONTH_MAP[key]
            break
    if month is None:
        return ParseResult(value=None, ok=False, error="BAD_MONTH", meta={"mon": mon})
    return ParseResult(value=(int(day), month, year), ok=True)


def parse_amount(text: str) -> ParseResult:
    if not text:
        return ParseResult(value=None, ok=False, error="EMPTY")
    s = normalize_digits(text)
    m = _AMOUNT_RX.search(s)
    if m:
        token = m.group(0)
    else:
        # Fallback: keep only digits and separators , . then attempt smart split
        token = re.sub(r"[^\d\.,]", "", s)
        if not token:
            return ParseResult(value=None, ok=False, error="NO_MATCH", meta={"text": text})
    # Smart parse: pick last separator as decimal if exactly 2 digits follow
    last_dot = token.rfind('.')
    last_com = token.rfind(',')
    idx = max(last_dot, last_com)
    val_str: Optional[str] = None
    if idx != -1 and len(token) - idx - 1 >= 2:
        frac = token[idx + 1: idx + 3]
        if len(frac) == 2 and frac.isdigit():
            int_part = re.sub(r"[\.,]", "", token[:idx])
            if int_part.isdigit():
                val_str = f"{int_part}.{frac}"
    if val_str is None:
        # If there is a single separator and 2 digits after it, treat as decimal
        m2 = re.search(r"^(\d{1,3}(?:[\.,]\d{3})*)[\.,](\d{2})$", token)
        if m2:
            int_part = re.sub(r"[\.,]", "", m2.group(1))
            frac = m2.group(2)
            val_str = f"{int_part}.{frac}"
    if val_str is None:
        # Last resort: remove all separators; if we have at least 1 digit, assume .00
        digits_only = re.sub(r"\D", "", token)
        if digits_only:
            val_str = f"{digits_only}.00"
    if val_str is None:
        return ParseResult(value=None, ok=False, error="BAD_NUMBER", meta={"text": text})
    try:
        return ParseResult(value=float(val_str), ok=True)
    except ValueError:
        return ParseResult(value=None, ok=False, error="BAD_NUMBER", meta={"text": text, "val": val_str})


def parse_cheque_number(text: str) -> ParseResult:
    if not text:
        return ParseResult(value=None, ok=False, error="EMPTY")
    s = normalize_digits(text)
    m = _CHEQUE_RX.search(s)
    if not m:
        return ParseResult(value=None, ok=False, error="NO_MATCH", meta={"text": text})
    return ParseResult(value=m.group(0), ok=True)


def normalize_name(text: str) -> ParseResult:
    if not text:
        return ParseResult(value=None, ok=False, error="EMPTY")
    # Apply Arabic shaping + bidi for display so names are not reversed visually.
    s = fix_arabic_text(text, for_display=True)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < 3:
        return ParseResult(value=None, ok=False, error="TOO_SHORT")
    return ParseResult(value=s, ok=True)

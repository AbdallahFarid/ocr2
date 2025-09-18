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


_DATE_RX = re.compile(r"\b(\d{1,2})[\-/](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\-/](\d{2,4})\b", re.I)
_AMOUNT_RX = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
_CHEQUE_RX = re.compile(r"\b\d{6,}\b")

_MONTH_MAP = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def parse_date(text: str) -> ParseResult:
    if not text:
        return ParseResult(value=None, ok=False, error="EMPTY")
    s = normalize_digits(text)
    m = _DATE_RX.search(s)
    if not m:
        return ParseResult(value=None, ok=False, error="NO_MATCH", meta={"text": text})
    day, mon, yr = m.group(1), m.group(2).title(), m.group(3)
    year = int(yr)
    if year < 100:
        year += 2000
    try:
        month = _MONTH_MAP[mon]
    except KeyError:
        return ParseResult(value=None, ok=False, error="BAD_MONTH", meta={"mon": mon})
    return ParseResult(value=(int(day), month, year), ok=True)


def parse_amount(text: str) -> ParseResult:
    if not text:
        return ParseResult(value=None, ok=False, error="EMPTY")
    s = normalize_digits(text)
    m = _AMOUNT_RX.search(s)
    if not m:
        return ParseResult(value=None, ok=False, error="NO_MATCH", meta={"text": text})
    amt = m.group(0).replace(",", "")
    try:
        return ParseResult(value=float(amt), ok=True)
    except ValueError:
        return ParseResult(value=None, ok=False, error="BAD_NUMBER", meta={"text": text})


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
    # Keep logical Arabic (no display shaping). Browsers handle shaping; reshaping can cause isolated forms.
    s = fix_arabic_text(text, for_display=False)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < 3:
        return ParseResult(value=None, ok=False, error="TOO_SHORT")
    return ParseResult(value=s, ok=True)

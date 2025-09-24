from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Iterable, Optional

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover - defensive
    ZoneInfo = None  # type: ignore

_DEFAULT_TZ = os.getenv("BATCH_TZ", "Africa/Cairo")


def cairo_today(now: Optional[datetime] = None) -> date:
    """Return today's date in Egypt local time (Africa/Cairo) if available.

    - If ZoneInfo is available and the zone exists, convert `now` to Africa/Cairo and return the date.
    - If unavailable, gracefully fall back to the UTC date (no crash).
    - If `now` is None, current UTC time is used to compute the date.
    """
    _now = now or datetime.utcnow().replace(tzinfo=timezone.utc)
    if _now.tzinfo is None:
        _now = _now.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(_DEFAULT_TZ)
            return _now.astimezone(tz).date()
        except Exception:
            pass
    # Fallback: UTC date
    return _now.date()


def format_batch_name(d: date, bank_code: str, seq: int) -> str:
    """Format name as DD_MM_YYYY_<BANK>_<NN> with NN two digits (01, 02, ...)."""
    return f"{d.day:02d}_{d.month:02d}_{d.year}_{bank_code}_{seq:02d}"


def _parse_seq_from_name(name: str, *, bank_code: str, d: date) -> Optional[int]:
    """Given a formatted batch name, return seq if it matches (date, bank), else None."""
    # Expected: DD_MM_YYYY_<BANK>_<NN>
    parts = name.split("_")
    if len(parts) < 5:
        return None
    dd, mm, yyyy, bank, nn = parts[0], parts[1], parts[2], parts[3], parts[4]
    if bank != bank_code:
        return None
    try:
        if int(dd) != d.day or int(mm) != d.month or int(yyyy) != d.year:
            return None
        return int(nn)
    except Exception:
        return None


@dataclass(frozen=True)
class BatchIdentity:
    batch_date: date
    seq: int
    name: str


def compute_next_identity(
    bank_code: str,
    existing_names: Iterable[str] | None = None,
    *,
    now: Optional[datetime] = None,
) -> BatchIdentity:
    """Compute next (batch_date, seq, name) without DB, based on existing names provided.

    - Chooses Egypt local date if possible; otherwise UTC date.
    - Scans provided `existing_names` to find the max seq for this (date, bank), returns next.
    - If no existing names provided or none match, seq starts at 1.
    """
    d = cairo_today(now)
    max_seq = 0
    for n in existing_names or []:
        s = _parse_seq_from_name(n, bank_code=bank_code, d=d)
        if s and s > max_seq:
            max_seq = s
    next_seq = max_seq + 1
    return BatchIdentity(batch_date=d, seq=next_seq, name=format_batch_name(d, bank_code, next_seq))

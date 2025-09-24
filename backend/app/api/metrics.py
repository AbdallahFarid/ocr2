from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.constants.banks import ALLOWED_BANKS
from app.api.review import get_audit_root

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _parse_iso8601(ts: str | None) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Support basic ISO8601 with Z or offset
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/kpi/per-bank")
async def kpi_per_bank(
    from_: str | None = Query(None, alias="from", description="Start ISO date/time inclusive"),
    to: str | None = Query(None, alias="to", description="End ISO date/time inclusive"),
) -> Dict[str, Dict[str, Any]]:
    """Aggregate KPIs by scanning audit JSONs (no DB).

    - Excludes the `name` field from field-level metrics.
    - A cheque is considered "with errors" if it has >=1 correction record for any field other than `name`.
    - Field error rate is incorrect_fields / total_fields across included cheques.
    - Date filtering is applied against the audit JSON `generated_at` timestamp.
    """
    start = _parse_iso8601(from_) if from_ else None
    end = _parse_iso8601(to) if to else None

    root: Path = get_audit_root()
    if not root.exists():
        return {}

    OUT: Dict[str, Dict[str, Any]] = {}

    for bank_dir in root.iterdir():
        if not bank_dir.is_dir():
            continue
        bank = bank_dir.name
        if bank not in ALLOWED_BANKS:
            continue

        total_cheques = 0
        cheques_with_errors = 0
        total_fields = 0
        incorrect_fields = 0

        for jf in bank_dir.glob("*.json"):
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            gen_at = _parse_iso8601(data.get("generated_at"))
            if start and (not gen_at or gen_at < start):
                continue
            if end and (not gen_at or gen_at > end):
                continue

            fields: Dict[str, Any] = data.get("fields") or {}
            # Exclude name field from field counts
            field_keys = [k for k in fields.keys() if k != "name"]
            total_fields += len(field_keys)

            total_cheques += 1

            corrections = data.get("corrections") or []
            corrected_fields = {c.get("field") for c in corrections if c.get("field") and c.get("field") != "name"}
            if corrected_fields:
                cheques_with_errors += 1
                incorrect_fields += len(corrected_fields)

        cheque_error_rate = (cheques_with_errors / total_cheques) if total_cheques else 0.0
        field_error_rate = (incorrect_fields / total_fields) if total_fields else 0.0

        OUT[bank] = {
            "total_cheques": total_cheques,
            "cheques_with_errors": cheques_with_errors,
            "cheque_error_rate": cheque_error_rate,
            "total_fields": total_fields,
            "incorrect_fields": incorrect_fields,
            "field_error_rate": field_error_rate,
        }

    return OUT

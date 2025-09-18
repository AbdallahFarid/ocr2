from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional
import csv


@dataclass
class DecisionRecord:
    decision: str  # "auto_approve" | "review"
    stp: bool
    overall_conf: float
    low_conf_fields: list[str]
    reasons: list[str]


def write_audit_json(
    *,
    bank: str,
    file_id: str,
    decision: Mapping[str, Any],
    per_field: Mapping[str, Mapping[str, Any]],
    out_dir: str,
    source_csv: Optional[str] = None,
    correlation_id: Optional[str] = None,
    extra_meta: Optional[Mapping[str, Any]] = None,
) -> str:
    """Write a standardized audit JSON file.

    Schema (v1):
      - schema_version: 1
      - generated_at: ISO8601 UTC timestamp
      - correlation_id: optional
      - bank, file
      - source_csv: optional reference to the field-level CSV used
      - decision: { decision, stp, overall_conf, low_conf_fields[], reasons[] }
      - fields: mapping field -> { field_conf, loc_conf, ocr_conf, parse_ok, parse_norm, ocr_text, ocr_lang, meets_threshold, validation? }
      - meta: optional
    """
    os.makedirs(out_dir, exist_ok=True)
    bank_dir = os.path.join(out_dir, str(bank))
    os.makedirs(bank_dir, exist_ok=True)

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "bank": bank,
        "file": file_id,
        "source_csv": source_csv,
        "decision": dict(decision),
        "fields": {k: dict(v) for k, v in per_field.items()},
        "meta": dict(extra_meta) if extra_meta else {},
    }
    out_path = os.path.join(bank_dir, f"{file_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def append_corrections(
    *,
    audit_path: str,
    reviewer_id: str,
    updates: Mapping[str, Mapping[str, Any]],
    reason_by_field: Optional[Mapping[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    """Append corrections to an existing audit JSON file and update field parse_norm.

    Returns the updated JSON payload as a dict.
    """
    # Load existing payload
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Audit file not found: {audit_path}")

    fields = payload.get("fields") or {}
    bank = str(payload.get("bank", ""))
    file_id = str(payload.get("file", ""))
    now_iso = datetime.now(timezone.utc).isoformat()
    corr_list = payload.get("corrections")
    if not isinstance(corr_list, list):
        corr_list = []

    updated = []
    for field_name, update in updates.items():
        rec = fields.get(field_name)
        if not isinstance(rec, dict):
            continue
        before = rec.get("parse_norm")
        after = str(update.get("value"))
        rec["parse_norm"] = after
        corr = {
            "reviewer_id": reviewer_id,
            "field": field_name,
            "before": before,
            "after": after,
            "reason": (reason_by_field or {}).get(field_name),
            "at": now_iso,
        }
        corr_list.append(corr)
        updated.append(field_name)

    payload["corrections"] = corr_list
    payload["fields"] = fields

    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Also append to a corrections CSV for template/dataset updates queue
    try:
        corr_out = os.getenv("CORRECTIONS_OUT") or os.path.join(
            "backend", "reports", "pipeline", "corrections", "corrections.csv"
        )
        os.makedirs(os.path.dirname(corr_out), exist_ok=True)
        header = [
            "bank",
            "file",
            "field",
            "before",
            "after",
            "reason",
            "reviewer_id",
            "at",
        ]
        write_header = not os.path.exists(corr_out)
        with open(corr_out, "a", newline="", encoding="utf-8") as cf:
            w = csv.writer(cf)
            if write_header:
                w.writerow(header)
            for field_name in updated:
                # find the matching correction record we just added
                # the last matching entry for this field has latest timestamp
                recs = [c for c in corr_list if c.get("field") == field_name and c.get("at") == now_iso]
                if recs:
                    c = recs[-1]
                    w.writerow(
                        [
                            bank,
                            file_id,
                            field_name,
                            c.get("before"),
                            c.get("after"),
                            c.get("reason"),
                            c.get("reviewer_id"),
                            c.get("at"),
                        ]
                    )
    except Exception:
        # CSV queue is best-effort; do not fail API
        pass

    return payload

from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Any, Dict, List

from app.services.routing import decide_route
from app.validations.gates import (
    validate_amount,
    validate_cheque_number,
    validate_date,
    validate_payee,
)
from app.persistence.audit import write_audit_json as persist_write_audit_json


def aggregate(field_csv: str, out_csv: str, *, write_audit: bool = False, audit_dir: str = "", correlation_id: str = "") -> str:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    with open(field_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
    for row in rows:
        file = row.get("file") or ""
        if not file:
            # skip errors or malformed
            continue
        groups.setdefault(file, []).append(row)

    out_path = out_csv
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "file",
            "bank",
            "decision",
            "stp",
            "overall_conf",
            "low_conf_fields",
            "reasons",
        ])
        for file, items in groups.items():
            # Build per_field map expected by decide_route
            per_field: Dict[str, Dict[str, Any]] = {}
            bank = items[0].get("bank", "")
            for it in items:
                field = (it.get("field") or "").strip()
                if not field:
                    continue
                # Extract confidences and parse flags
                try:
                    field_conf = float(it.get("field_conf") or 0.0)
                except Exception:
                    field_conf = 0.0
                parse_ok = str(it.get("parse_ok") or "false").strip().lower() == "true"
                loc_conf = float(it.get("loc_conf") or 0.0)
                ocr_conf = float(it.get("ocr_conf") or 0.0)
                rec: Dict[str, Any] = {"field_conf": field_conf, "loc_conf": loc_conf, "ocr_conf": ocr_conf}
                # Attach validation results if we can
                val = None
                parse_norm = it.get("parse_norm") or ""
                ocr_text = it.get("ocr_text") or ""
                ocr_lang = it.get("ocr_lang") or ""
                meets_threshold = str(it.get("meets_threshold") or "false").strip().lower() == "true"
                if field == "date" and parse_norm:
                    vr = validate_date(parse_norm)
                    val = {"ok": bool(vr.ok), "code": vr.code.value}
                elif field == "amount_numeric" and parse_norm:
                    try:
                        amt_val = float(parse_norm)
                    except Exception:
                        amt_val = None
                    vr = validate_amount(amt_val)
                    val = {"ok": bool(vr.ok), "code": vr.code.value}
                elif field == "cheque_number" and parse_norm:
                    vr = validate_cheque_number(parse_norm, bank_id=bank)
                    val = {"ok": bool(vr.ok), "code": vr.code.value}
                elif field == "name":
                    # Without a master list, just basic presence/length
                    vr = validate_payee(parse_norm or ocr_text, master=None)
                    val = {"ok": bool(vr.ok), "code": vr.code.value}
                if val is not None:
                    rec["validation"] = val
                # Keep other display info for audit
                rec.update({
                    "parse_ok": parse_ok,
                    "parse_norm": parse_norm,
                    "ocr_text": ocr_text,
                    "ocr_lang": ocr_lang,
                    "meets_threshold": meets_threshold,
                })
                per_field[field] = rec
            d = decide_route(per_field)
            w.writerow([
                file,
                bank,
                d.decision,
                str(bool(d.stp)).lower(),
                f"{float(d.overall_conf):.3f}",
                ";".join(d.low_conf_fields),
                ";".join(d.reasons),
            ])
            # Optional audit JSON per image
            if write_audit and audit_dir:
                persist_write_audit_json(
                    bank=str(bank),
                    file_id=str(file),
                    decision={
                        "decision": d.decision,
                        "stp": bool(d.stp),
                        "overall_conf": float(d.overall_conf),
                        "low_conf_fields": list(d.low_conf_fields),
                        "reasons": list(d.reasons),
                    },
                    per_field=per_field,
                    out_dir=str(audit_dir),
                    source_csv=field_csv,
                    correlation_id=correlation_id or None,
                    extra_meta=None,
                )
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate field-level pipeline CSV into routing decisions")
    ap.add_argument("field_csv", help="Input CSV from pipeline_eval")
    ap.add_argument("out_csv", help="Output decisions CSV")
    ap.add_argument("--write-audit-json", action="store_true", help="Write per-image audit JSON files")
    ap.add_argument("--audit-dir", default="backend/reports/pipeline/audit", help="Audit JSON output root directory")
    ap.add_argument("--correlation-id", default="", help="Optional correlation ID to include in audit JSONs")
    args = ap.parse_args()
    path = aggregate(
        args.field_csv,
        args.out_csv,
        write_audit=bool(args.write_audit_json),
        audit_dir=str(args.audit_dir),
        correlation_id=str(args.correlation_id),
    )
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

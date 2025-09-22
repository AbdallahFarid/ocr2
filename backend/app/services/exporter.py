from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from openpyxl import Workbook  # type: ignore
except Exception:  # pragma: no cover - test env may install later
    Workbook = None  # type: ignore


# --- Domain and schema ---

# NOTE: 'name' muted by request — keep code but do not require it for export validation
REQUIRED_FIELDS = ("date", "cheque_number", "amount_numeric")


@dataclass
class ExportRow:
    bank: str
    file: str
    date: Optional[str]
    cheque_number: Optional[str]
    amount_numeric: Optional[str]
    name: Optional[str]
    stp: bool
    overall_conf: float

    def as_list(self, headers: Sequence[str]) -> List[Any]:
        data: Dict[str, Any] = {
            "bank": self.bank,
            "file": self.file,
            "date": self.date,
            "cheque_number": self.cheque_number,
            "amount_numeric": self.amount_numeric,
            "name": self.name,
            "stp": self.stp,
            "overall_conf": self.overall_conf,
        }
        return [data.get(h) for h in headers]


# NOTE: 'name' muted from CSV headers — can be re-added later
DEFAULT_HEADERS: Tuple[str, ...] = (
    "bank",
    "file",
    "date",
    "cheque_number",
    "amount_numeric",
    # "name",
    "stp",
    "overall_conf",
)


def _is_approved(payload: Mapping[str, Any]) -> bool:
    d = payload.get("decision") or {}
    # Consider approved if decision is auto_approve or stp=True
    decision = str(d.get("decision", "")).lower()
    stp = bool(d.get("stp", False))
    return decision == "auto_approve" or stp is True

def _is_validated(payload: Mapping[str, Any]) -> bool:
    fields = payload.get("fields") or {}
    if not isinstance(fields, Mapping):
        return False
    for key in REQUIRED_FIELDS:
        rec = fields.get(key)
        if not isinstance(rec, Mapping):
            return False
        v = rec.get("validation") or {}
        if not isinstance(v, Mapping) or not bool(v.get("ok", False)):
            return False
    return True


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def iter_audit_items(audit_root: str | os.PathLike[str]) -> Iterable[Dict[str, Any]]:
    root = Path(audit_root)
    if not root.exists():
        return []
    for bank_dir in root.iterdir():
        if not bank_dir.is_dir():
            continue
        for p in bank_dir.glob("*.json"):
            data = _load_json(p)
            if not data:
                continue
            yield data


def validate_schema(payload: Mapping[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(payload.get("bank"), str):
        errors.append("bank: missing or not a string")
    if not isinstance(payload.get("file"), str):
        errors.append("file: missing or not a string")
    fields = payload.get("fields") or {}
    if not isinstance(fields, Mapping):
        errors.append("fields: missing or not a mapping")
        return False, errors
    for key in REQUIRED_FIELDS:
        rec = fields.get(key)
        if not isinstance(rec, Mapping):
            errors.append(f"fields.{key}: missing")
            continue
        # parse_norm is the canonical export value when available, fallback to ocr_text
        value = rec.get("parse_norm")
        if value in (None, ""):
            value = rec.get("ocr_text")
        if value in (None, ""):
            errors.append(f"fields.{key}: empty")
    return len(errors) == 0, errors


def build_row(payload: Mapping[str, Any]) -> ExportRow:
    fields = payload.get("fields") or {}

    def getv(k: str) -> Optional[str]:
        rec = fields.get(k) or {}
        v = rec.get("parse_norm")
        if v in (None, ""):
            v = rec.get("ocr_text")
        return None if v in (None, "") else str(v)

    d = payload.get("decision") or {}
    return ExportRow(
        bank=str(payload.get("bank", "")),
        file=str(payload.get("file", "")),
        date=getv("date"),
        cheque_number=getv("cheque_number"),
        amount_numeric=getv("amount_numeric"),
        name=getv("name"),
        stp=bool(d.get("stp", False)),
        overall_conf=float(d.get("overall_conf", 0.0) or 0.0),
    )


def gather_approved_rows(audit_root: str | os.PathLike[str]) -> List[ExportRow]:
    rows: List[ExportRow] = []
    for payload in iter_audit_items(audit_root):
        if not _is_approved(payload):
            continue
        # Require item-level validation
        if not _is_validated(payload):
            continue
        ok, _ = validate_schema(payload)
        if not ok:
            continue
        rows.append(build_row(payload))
    return rows


def export_csv(dest_path: str | os.PathLike[str], rows: Sequence[ExportRow], headers: Sequence[str] = DEFAULT_HEADERS) -> str:
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(headers))
        for r in rows:
            w.writerow(r.as_list(headers))
    return str(dest)


def export_xlsx(dest_path: str | os.PathLike[str], rows: Sequence[ExportRow], headers: Sequence[str] = DEFAULT_HEADERS) -> str:
    if Workbook is None:
        raise RuntimeError("openpyxl is not installed; cannot export xlsx")
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "cheques"
    ws.append(list(headers))
    for r in rows:
        ws.append(r.as_list(headers))
    wb.save(str(dest))
    return str(dest)

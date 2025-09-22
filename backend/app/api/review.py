from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Response
from pydantic import BaseModel
import csv
import io
import json

from app.schemas.review import ReviewItem, CorrectionPayload, CorrectionResult
from app.persistence.audit import append_corrections
from app.services.upload import save_upload_and_process

router = APIRouter(prefix="/review", tags=["review"])

def get_audit_root() -> Path:
    """Resolve the audit root dynamically from environment each call.

    This allows tests to override AUDIT_ROOT via monkeypatch before requests.
    """
    return Path(os.getenv("AUDIT_ROOT", "backend/reports/pipeline/audit"))


def _audit_path(bank: str, file_id: str) -> str:
    return str(get_audit_root() / bank / f"{file_id}.json")


@router.get("/items", response_model=List[Dict[str, Any]])
async def list_items() -> List[Dict[str, Any]]:
    root = get_audit_root()
    if not root.exists():
        return []
    items: List[Dict[str, Any]] = []
    for bank_dir in root.iterdir():
        if not bank_dir.is_dir():
            continue
        for f in bank_dir.glob("*.json"):
            items.append({"bank": bank_dir.name, "file": f.stem})
    # Stable order for tests/UX
    items.sort(key=lambda x: (x["bank"], x["file"]))
    return items


@router.get("/items/{bank}/{file_id}", response_model=ReviewItem)
async def get_item(request: Request, bank: str, file_id: str) -> ReviewItem:
    import json

    p = _audit_path(bank, file_id)
    if not Path(p).exists():
        raise HTTPException(status_code=404, detail="Audit JSON not found")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Ensure imageUrl is populated; compute from request base URL if missing
    if not data.get("imageUrl"):
        base = str(request.base_url).rstrip('/')
        data["imageUrl"] = f"{base}/files/{bank}/{file_id}"
    return ReviewItem(**data)


@router.post("/items/{bank}/{file_id}/corrections", response_model=CorrectionResult)
async def submit_corrections(bank: str, file_id: str, payload: CorrectionPayload) -> CorrectionResult:
    p = _audit_path(bank, file_id)
    if not Path(p).exists():
        raise HTTPException(status_code=404, detail="Audit JSON not found")

    updated = append_corrections(
        audit_path=p,
        reviewer_id=payload.reviewer_id,
        updates={k: v.model_dump() for k, v in payload.updates.items()},
        reason_by_field={k: v.reason for k, v in payload.updates.items()},
    )
    return CorrectionResult(
        ok=True,
        updated_fields=list(payload.updates.keys()),
        corrections_appended=[],
    )


def get_upload_root() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "backend/uploads"))


@router.post("/upload")
async def upload_cheque(
    request: Request,
    bank: str = Form(..., description="Bank code, e.g. QNB, FABMISR, BANQUE_MISR, CIB, AAIB, or NBE"),
    file: UploadFile = File(...),
    correlation_id: str | None = Form(None),
) -> Dict[str, Any]:
    bank = bank.strip().upper()
    if bank not in {"QNB", "FABMISR", "BANQUE_MISR", "CIB", "AAIB", "NBE"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported bank. Use QNB, FABMISR, BANQUE_MISR, CIB, AAIB, or NBE.",
        )

    # Validate content type and size (read into memory; adjust for large files if needed)
    allowed_ct = {"image/jpeg", "image/jpg", "image/png", "image/tiff"}
    if file.content_type and file.content_type.lower() not in allowed_ct:
        # Some browsers may omit or vary; we'll also rely on extension fallback in service
        pass

    data = await file.read()
    max_mb = float(os.getenv("MAX_UPLOAD_MB", "20"))
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {int(max_mb)} MB")

    # Determine public base from request base_url
    public_base = str(request.base_url).rstrip('/')

    file_id, item = save_upload_and_process(
        upload_dir=str(get_upload_root()),
        audit_root=str(get_audit_root()),
        bank=bank,
        file_bytes=data,
        original_filename=file.filename or "upload.jpg",
        correlation_id=correlation_id,
        public_base=public_base,
    )

    return {
        "ok": True,
        "bank": bank,
        "file": file_id,
        "imageUrl": item.get("imageUrl"),
        "reviewUrl": f"/review/{bank}/{file_id}",
        "item": item,
    }


class ExportItem(BaseModel):
    bank: str
    file: str


class ExportRequest(BaseModel):
    items: list[ExportItem]
    overrides: dict[str, dict[str, str]] | None = None  # key: "BANK/FILE" -> { field: value }
    format: str = "csv"  # currently only csv


@router.post("/export")
async def export_items(req: ExportRequest) -> Response:
    # Build CSV in-memory; apply overrides to parse_norm (and mirror into ocr_text for Arabic) per item
    # 'name' muted from export; keep code commented for later reintroduction
    headers = [
        "Bank",
        "date",
        "cheque number",
        "amount",
        # "name",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for it in req.items:
        bank = it.bank.strip()
        file_id = it.file.strip()
        p = _audit_path(bank, file_id)
        if not Path(p).exists():
            # Skip missing
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = data.get("fields") or {}
        key = f"{bank}/{file_id}"
        ov = (req.overrides or {}).get(key) or {}
        # Apply overrides to parse_norm; mirror into ocr_text for Arabic
        for k, v in ov.items():
            rec = fields.get(k)
            if isinstance(rec, dict):
                rec["parse_norm"] = str(v)
                if rec.get("ocr_lang") == "ar":
                    rec["ocr_text"] = str(v)
        def getv(name: str) -> str | None:
            rec = fields.get(name) or {}
            v = rec.get("parse_norm")
            if v in (None, ""):
                v = rec.get("ocr_text")
            return None if v in (None, "") else str(v)
        row = [
            bank,
            getv("date"),
            getv("cheque_number"),
            getv("amount_numeric"),
            # getv("name"),
        ]
        w.writerow(row)

    # Prepend UTF-8 BOM so Excel detects UTF-8 and renders Arabic correctly
    content = "\ufeff" + buf.getvalue()
    resp = Response(content=content, media_type="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = "attachment; filename=cheques.csv"
    return resp

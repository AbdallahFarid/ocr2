from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Response, BackgroundTasks
from pydantic import BaseModel
import csv
import io
import json
import zipfile
import time
from datetime import datetime, timezone
import numpy as np
import cv2
import logging
import copy

from app.schemas.review import ReviewItem, CorrectionPayload, CorrectionResult
from app.persistence.audit import append_corrections
from app.services.upload import save_upload_and_process
from app.constants.banks import ALLOWED_BANKS
from app.db.session import db_enabled, session_scope
from app.db import crud as dbcrud

router = APIRouter(prefix="/review", tags=["review"])

def get_audit_root() -> Path:
    """Resolve the audit root dynamically from environment each call.

    This allows tests to override AUDIT_ROOT via monkeypatch before requests.
    """
    return Path(os.getenv("AUDIT_ROOT", "backend/reports/pipeline/audit"))


def _as_upload_file(obj):
    """Return obj if it looks like an UploadFile (duck-typed), else None."""
    if obj is None:
        return None
    if hasattr(obj, "filename") and hasattr(obj, "read"):
        return obj
    return None


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
async def submit_corrections(
    bank: str,
    file_id: str,
    payload: CorrectionPayload,
    background_tasks: BackgroundTasks,
) -> CorrectionResult:
    # Normalize inputs for DB lookups
    bank = bank.strip().upper()
    file_id = file_id.strip()

    p = _audit_path(bank, file_id)
    if not Path(p).exists():
        raise HTTPException(status_code=404, detail="Audit JSON not found")

    # Read previous values to pass to DB corrections
    try:
        with open(p, "r", encoding="utf-8") as f:
            prev_payload = json.load(f)
            prev_fields = prev_payload.get("fields") or {}
    except Exception:
        prev_fields = {}

    updated = append_corrections(
        audit_path=p,
        reviewer_id=payload.reviewer_id,
        updates={k: v.model_dump() for k, v in payload.updates.items()},
        reason_by_field={k: v.reason for k, v in payload.updates.items()},
    )
    # Mirror to DB (best effort)
    try:
        if db_enabled():
            at_dt = datetime.now(timezone.utc)
            corrs: dict[str, dict[str, Any]] = {}
            for fname, upd in payload.updates.items():
                before = None
                try:
                    prev = (prev_fields.get(fname) or {})
                    before = prev.get("parse_norm")
                    if before in (None, ""):
                        before = prev.get("ocr_text")
                except Exception:
                    before = None
                corrs[fname] = {
                    "before": before,
                    "after": upd.value,
                    "reason": upd.reason,
                }
            # Apply and then trigger KPI recompute for the parent batch in background
            batch_name: str | None = None
            with session_scope() as db:
                dbcrud.apply_corrections(
                    db,
                    bank_code=bank,
                    file_id=file_id,
                    corrections=corrs,
                    reviewer_id=payload.reviewer_id,
                    at=at_dt,
                )
                # Find cheque and its batch to recompute KPIs
                from app.db.models import Batch as BatchModel
                ch = dbcrud.find_cheque_by_bank_file(db, bank_code=bank, file_id=file_id)
                if ch:
                    b = db.get(BatchModel, ch.batch_id)
                    if b:
                        batch_name = b.name
            if batch_name:
                background_tasks.add_task(_bg_recompute_kpis, bank_code=bank, batch_name=batch_name)
    except Exception:
        # Do not fail API if DB write fails, but log for diagnostics
        logging.getLogger(__name__).exception("DB mirror for corrections failed")
    return CorrectionResult(
        ok=True,
        updated_fields=list(payload.updates.keys()),
        corrections_appended=[],
    )


def get_upload_root() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "backend/uploads"))


def _batch_map_root() -> Path:
    return Path(os.getenv("BATCH_MAP_DIR", "backend/.batch_map"))


def _sanitize(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum() or ch in ("-", "_"))[:128]


def _get_or_create_batch_identity(bank: str, correlation_id: Optional[str]) -> Optional[tuple[str, str, int]]:
    """
    Determine a batch identity for this upload session.

    - If correlation_id is provided and DB is enabled, create/read a mapping file under backend/.batch_map
      so that multiple requests with the same correlation_id share the same batch.
    - Otherwise, compute a fresh identity for this request (DB enabled). Returns (batch_name, batch_date_iso, seq).
    - If DB is not enabled, returns None.
    """
    if not db_enabled():
        return None
    from app.services.batches import cairo_today, format_batch_name

    d = cairo_today()
    if correlation_id:
        root = _batch_map_root() / bank
        try:
            root.mkdir(parents=True, exist_ok=True)
            key = _sanitize(str(correlation_id)) or "anon"
            p = root / f"{key}.txt"
            if p.exists():
                try:
                    txt = p.read_text(encoding="utf-8").strip()
                    if txt:
                        name, dstr, seqs = txt.split("|")
                        return name, dstr, int(seqs)
                except Exception:
                    pass
            # Compute and persist mapping
            with session_scope() as db:
                max_seq = dbcrud.get_max_seq_for_bank_date(db, bank_code=bank, d=d)
            next_seq = max_seq + 1
            batch_name = format_batch_name(d, bank, next_seq)
            try:
                p.write_text(f"{batch_name}|{d.isoformat()}|{next_seq}", encoding="utf-8")
            except Exception:
                pass
            return batch_name, d.isoformat(), next_seq
        except Exception:
            # Fallback to direct compute below
            pass

    # No correlation_id or failed mapping: compute fresh identity for this request
    with session_scope() as db:
        max_seq = dbcrud.get_max_seq_for_bank_date(db, bank_code=bank, d=d)
    next_seq = max_seq + 1
    batch_name = format_batch_name(d, bank, next_seq)
    return batch_name, d.isoformat(), next_seq


def _bg_recompute_kpis(bank_code: str, batch_name: str) -> None:
    try:
        if not db_enabled():
            return
        with session_scope() as db:
            dbcrud.recompute_and_update_batch_kpis_by_name(db, bank_code=bank_code, batch_name=batch_name)
    except Exception:
        # best-effort background job
        pass


def _resolve_correlation_map(bank: str, correlation_id: str) -> tuple[Optional[str], Optional[Path]]:
    root = _batch_map_root() / bank
    key = _sanitize(str(correlation_id)) or "anon"
    p = root / f"{key}.txt"
    if not p.exists():
        return None, None
    try:
        txt = p.read_text(encoding="utf-8").strip()
        if not txt:
            return None, p
        name, dstr, seqs = txt.split("|")
        return name, p
    except Exception:
        return None, p


@router.post("/batches/finalize")
async def finalize_batch(
    bank: str = Form(..., description="Bank code"),
    correlation_id: str = Form(..., description="Upload session correlation id"),
) -> Dict[str, Any]:
    """Finalize a multi-file upload session (by correlation_id) and recompute KPIs.

    This sets processing_ended_at and processing_ms for the batch and performs a final KPI recompute.
    Idempotent: if already finalized, will recompute again and succeed.
    """
    bank = bank.strip().upper()
    if bank not in ALLOWED_BANKS:
        raise HTTPException(status_code=400, detail="Unsupported bank.")
    if not correlation_id or not correlation_id.strip():
        raise HTTPException(status_code=400, detail="Missing correlation_id")

    batch_name, path_obj = _resolve_correlation_map(bank, correlation_id)
    if not batch_name:
        raise HTTPException(status_code=404, detail="Unknown correlation_id or no batch mapping found")

    # Synchronously recompute & update KPIs (also sets ended_at/ms inside CRUD helper)
    # Respect env toggle: if DATABASE_URL is not set, treat DB as disabled regardless of prior engine state
    if not os.getenv("DATABASE_URL") or not db_enabled():
        raise HTTPException(status_code=503, detail="DB not enabled")
    metrics: dict[str, Any] | None = None
    try:
        # Ensure schema exists on the current engine (useful for SQLite tests)
        try:
            from app.db.models import Base
            from app.db.session import get_engine
            eng = get_engine()
            if eng is not None:
                Base.metadata.create_all(eng)
        except Exception:
            pass
        # First, mark batch as ended now to guarantee timestamps even if KPI recompute is a no-op
        try:
            from datetime import datetime, timezone
            from app.db.models import Batch as BatchModel
            with session_scope() as db:
                b = db.query(BatchModel).filter(BatchModel.bank_code == bank, BatchModel.name == batch_name).first()
                if b and b.processing_ended_at is None:
                    ended = datetime.now(timezone.utc)
                    b.processing_ended_at = ended
                    if b.processing_started_at:
                        delta = ended - b.processing_started_at
                        b.processing_ms = int(delta.total_seconds() * 1000)
        except Exception:
            pass
        with session_scope() as db:
            metrics = dbcrud.recompute_and_update_batch_kpis_by_name(db, bank_code=bank, batch_name=batch_name) or {}
            # Within the same transaction, ensure ended timestamp is present
            from app.db.models import Batch as BatchModel
            b = db.query(BatchModel).filter(BatchModel.bank_code == bank, BatchModel.name == batch_name).first()
            if b and b.processing_ended_at is None:
                from datetime import datetime, timezone
                ended = datetime.now(timezone.utc)
                b.processing_ended_at = ended
                if b.processing_started_at:
                    delta = ended - b.processing_started_at
                    b.processing_ms = int(delta.total_seconds() * 1000)
    except Exception:
        # As a last resort, mark batch ended even if KPI recompute failed (e.g., partial schema in tests)
        try:
            from datetime import datetime, timezone
            with session_scope() as db:
                from app.db.models import Batch as BatchModel
                b = db.query(BatchModel).filter(BatchModel.bank_code == bank, BatchModel.name == batch_name).first()
                if b:
                    ended = datetime.now(timezone.utc)
                    b.processing_ended_at = ended
                    if b.processing_started_at:
                        delta = ended - b.processing_started_at
                        b.processing_ms = int(delta.total_seconds() * 1000)
        except Exception:
            pass
    # Ensure ended timestamp is set even if recompute returned without updating it
    try:
        from datetime import datetime, timezone
        with session_scope() as db:
            from app.db.models import Batch as BatchModel
            b = db.query(BatchModel).filter(BatchModel.bank_code == bank, BatchModel.name == batch_name).first()
            if b and b.processing_ended_at is None:
                ended = datetime.now(timezone.utc)
                b.processing_ended_at = ended
                if b.processing_started_at:
                    delta = ended - b.processing_started_at
                    b.processing_ms = int(delta.total_seconds() * 1000)
    except Exception:
        pass

    # Best-effort: clear the mapping file
    try:
        if path_obj and path_obj.exists():
            path_obj.unlink(missing_ok=True)  # type: ignore[arg-type]
    except Exception:
        pass

    # Final fallback: enforce ended timestamp with a direct UPDATE if somehow still NULL
    try:
        from datetime import datetime, timezone
        from sqlalchemy import update
        from app.db.models import Batch as BatchModel
        with session_scope() as db:
            nowdt = datetime.now(timezone.utc)
            db.execute(
                update(BatchModel)
                .where(
                    BatchModel.bank_code == bank,
                    BatchModel.name == batch_name,
                    BatchModel.processing_ended_at.is_(None),
                )
                .values(processing_ended_at=nowdt)
            )
    except Exception:
        pass

    return {"ok": True, "bank": bank, "batch": batch_name, "metrics": metrics or {}}


@router.post("/upload")
async def upload_cheque(
    request: Request,
    background_tasks: BackgroundTasks,
    bank: str = Form(..., description="Bank code, e.g. QNB, FABMISR, BANQUE_MISR, CIB, AAIB, or NBE"),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    zip_file: UploadFile | None = File(None),
    correlation_id: str | None = Form(None),
) -> Dict[str, Any]:
    bank = bank.strip().upper()
    if bank not in ALLOWED_BANKS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported bank. Use QNB, FABMISR, BANQUE_MISR, CIB, AAIB, or NBE.",
        )

    # Determine public base from request base URL
    public_base = str(request.base_url).rstrip('/')

    # Prefer typed params if provided; fallback to parsing form if both missing
    file_obj = _as_upload_file(file)
    if file_obj and not (file_obj.filename or "").strip():
        file_obj = None
    zip_obj = _as_upload_file(zip_file)
    if zip_obj and not (zip_obj.filename or "").strip():
        zip_obj = None
    scanned_files: list[UploadFile] = []
    if not file_obj and not zip_obj:
        form = await request.form()
        f = form.get("file")
        z = form.get("zip_file")
        f2 = _as_upload_file(f)
        if f2 and (f2.filename or "").strip():
            file_obj = f2
        z2 = _as_upload_file(z)
        if z2 and (z2.filename or "").strip():
            zip_obj = z2
        # If still not found, scan all form values for any UploadFile entries
        if not file_obj and not zip_obj:
            found_files: list = []
            for key in form.keys():
                for v in form.getlist(key):
                    u = _as_upload_file(v)
                    if u and (u.filename or "").strip():
                        found_files.append(u)
            if len(found_files) == 1 and str(found_files[0].filename).lower().endswith(".zip"):
                zip_obj = found_files[0]
            elif found_files:
                # Treat as multiple files upload
                scanned_files = list(found_files)

    # Compute a batch identity for this request (if DB enabled) so all files go into same batch
    bi = _get_or_create_batch_identity(bank, correlation_id)
    db_batch_name = db_batch_date = None
    db_seq = None
    if bi:
        db_batch_name, dstr, db_seq = bi[0], bi[1], bi[2]
    # If a zip was provided, process all images within
    if _as_upload_file(zip_obj) and (zip_obj.filename or "").strip():
        zdata = await zip_obj.read()
        if not zdata:
            raise HTTPException(status_code=400, detail="Empty zip file")
        if bank not in ALLOWED_BANKS:
            raise HTTPException(status_code=400, detail="Unsupported bank.")

        upload_root = str(get_upload_root())
        audit_root = str(get_audit_root())
        items: list[dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(zdata)) as zf:
            idx = 0
            for zi in zf.infolist():
                n = zi.filename
                if zi.is_dir():
                    continue
                if (".." in n) or n.startswith("/") or n.startswith("\\"):
                    continue
                if not _allowed_image(n):
                    continue
                with zf.open(zi) as f:
                    data = f.read()
                # Optional content sniffing
                if os.getenv("UPLOAD_SNIFF", "0") == "1":
                    try:
                        arr = np.frombuffer(data, dtype=np.uint8)
                        img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                        if img is None:
                            continue
                    except Exception:
                        continue
                file_id, item = save_upload_and_process(
                    upload_dir=upload_root,
                    audit_root=audit_root,
                    bank=bank,
                    file_bytes=data,
                    original_filename=os.path.basename(n),
                    correlation_id=correlation_id,
                    public_base=public_base,
                    db_batch_name=db_batch_name,
                    db_batch_date=None,
                    db_seq=db_seq,
                    index_in_batch=idx,
                )
                idx += 1
                items.append({
                    "bank": bank,
                    "file": file_id,
                    "imageUrl": item.get("imageUrl"),
                    "reviewUrl": f"/review/{bank}/{file_id}",
                })

        if not items:
            raise HTTPException(status_code=400, detail="No valid images in zip")

        # Enqueue KPI recompute for this batch
        if db_batch_name:
            background_tasks.add_task(_bg_recompute_kpis, bank_code=bank, batch_name=db_batch_name)
        return {"ok": True, "count": len(items), "firstReviewUrl": items[0]["reviewUrl"], "items": items}

    # If multiple files were provided (non-zip), process all
    all_files: list[UploadFile] = []
    if files:
        for uf in files:
            u = _as_upload_file(uf)
            if u and (u.filename or "").strip():
                all_files.append(u)
    # Include any scanned files from raw form (e.g., multiple 'file' fields)
    if scanned_files:
        for uf in scanned_files:
            u = _as_upload_file(uf)
            if u and (u.filename or "").strip():
                all_files.append(u)
    single_mode = False
    if not all_files:
        # Fall back to single-file param
        if _as_upload_file(file_obj) and (file_obj.filename or "").strip():
            all_files = [file_obj]
            single_mode = True
        else:
            raise HTTPException(status_code=400, detail="Provide a file(s) or a zip_file")

    # Validate content type and size (read into memory; adjust for large files if needed)
    allowed_ct = {"image/jpeg", "image/jpg", "image/png", "image/tiff"}
    if getattr(file_obj, "content_type", None) and file_obj.content_type.lower() not in allowed_ct:
        # Some browsers may omit or vary; we'll also rely on extension fallback in service
        pass

    items: list[dict[str, Any]] = []
    upload_root = str(get_upload_root())
    audit_root = str(get_audit_root())
    max_mb = float(os.getenv("MAX_UPLOAD_MB", "20"))
    single_item_payload: dict[str, Any] | None = None
    for idx, uf in enumerate(all_files):
        data = await uf.read()
        if len(data) > max_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File too large: {uf.filename} (Max {int(max_mb)} MB)")
        # Optional content sniffing (reject non-image)
        if os.getenv("UPLOAD_SNIFF", "0") == "1":
            try:
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                if img is None:
                    raise ValueError("invalid image")
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid image content: {uf.filename}")
        file_id, item = save_upload_and_process(
            upload_dir=upload_root,
            audit_root=audit_root,
            bank=bank,
            file_bytes=data,
            original_filename=uf.filename or "upload.jpg",
            correlation_id=correlation_id,
            public_base=public_base,
            db_batch_name=db_batch_name,
            db_batch_date=None,
            db_seq=db_seq,
            index_in_batch=idx,
        )
        payload_entry = {
            "bank": bank,
            "file": file_id,
            "imageUrl": item.get("imageUrl"),
            "reviewUrl": f"/review/{bank}/{file_id}",
        }
        items.append(payload_entry)
        # If this is a single-file submission (not multi-file), prepare single response format
        if single_mode and len(all_files) == 1:
            single_item_payload = {
                "ok": True,
                "bank": bank,
                "file": file_id,
                "imageUrl": item.get("imageUrl"),
                "reviewUrl": f"/review/{bank}/{file_id}",
                "item": item,
            }

    # Enqueue KPI recompute for this batch
    if db_batch_name:
        background_tasks.add_task(_bg_recompute_kpis, bank_code=bank, batch_name=db_batch_name)
    # If this was a single-file upload (form field 'file'), return single-item payload
    if single_mode and single_item_payload is not None:
        return single_item_payload
    return {"ok": True, "count": len(items), "firstReviewUrl": items[0]["reviewUrl"], "items": items}


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
    # Track affected batches so we can mark them approved and recompute KPIs
    affected_batches: set[tuple[str, str]] = set()  # (bank_code, batch_name)
    for it in req.items:
        bank = it.bank.strip()
        bank_u = bank.upper()
        file_id = it.file.strip()
        p = _audit_path(bank, file_id)
        if not Path(p).exists():
            # Skip missing
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = data.get("fields") or {}
        # Take a deep copy BEFORE applying overrides so we have true "before" values
        prev_fields = copy.deepcopy(fields)
        key = f"{bank}/{file_id}"
        ov = (req.overrides or {}).get(key) or {}
        # Apply overrides to parse_norm; mirror into ocr_text for Arabic
        for k, v in ov.items():
            rec = fields.get(k)
            if isinstance(rec, dict):
                rec["parse_norm"] = str(v)
                if rec.get("ocr_lang") == "ar":
                    rec["ocr_text"] = str(v)
        # Persist overrides as corrections to the audit JSON and DB (best-effort)
        try:
            # 1) Update audit JSON with corrections
            if ov:
                from app.schemas.review import CorrectionFieldUpdate
                payload_updates = {k: {"value": str(v), "reason": None} for k, v in ov.items() if k != "name"}
                if payload_updates:
                    append_corrections(
                        audit_path=p,
                        reviewer_id="export",
                        updates=payload_updates,
                        reason_by_field=None,
                    )
            # 2) Mirror to DB as corrections and mark fields corrected
            if db_enabled() and ov:
                with session_scope() as db:
                    ch = dbcrud.find_cheque_by_bank_file(db, bank_code=bank_u, file_id=file_id)
                    if ch:
                        # Build corrections dict using BEFORE from current fields
                        corr_map: dict[str, dict[str, any]] = {}
                        for k, v in ov.items():
                            if k == "name":
                                continue  # muted
                            # Use original value from prev_fields captured before overrides
                            if isinstance(prev_fields, dict):
                                prev = (prev_fields.get(k) or {})
                                before = prev.get("parse_norm")
                                if before in (None, ""):
                                    before = prev.get("ocr_text")
                            else:
                                before = None
                            corr_map[k] = {"before": before, "after": str(v), "reason": None}
                        if corr_map:
                            dbcrud.apply_corrections(
                                db,
                                bank_code=bank_u,
                                file_id=file_id,
                                corrections=corr_map,
                                reviewer_id="export",
                                at=datetime.now(timezone.utc),
                            )
        except Exception:
            # Never block export on correction persistence
            logging.getLogger(__name__).exception("Failed to persist export overrides as corrections")
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

        # Best-effort: mark the DB batch as approved and record end time
        try:
            if db_enabled():
                from app.db.models import Batch as BatchModel
                with session_scope() as db:
                    ch = dbcrud.find_cheque_by_bank_file(db, bank_code=bank_u, file_id=file_id)
                    if ch:
                        b = db.get(BatchModel, ch.batch_id)
                        if b:
                            # Mark approved upon export
                            b.status = "approved"
                            if b.processing_ended_at is None:
                                ended = datetime.now(timezone.utc)
                                b.processing_ended_at = ended
                                if b.processing_started_at:
                                    delta = ended - b.processing_started_at
                                    b.processing_ms = int(delta.total_seconds() * 1000)
                            affected_batches.add((b.bank_code, b.name))
        except Exception:
            # export should not fail on DB errors
            pass

    # Prepend UTF-8 BOM so Excel detects UTF-8 and renders Arabic correctly
    content = "\ufeff" + buf.getvalue()
    # Recompute KPIs for affected batches (best-effort)
    try:
        if db_enabled():
            for bank_code, batch_name in affected_batches:
                with session_scope() as db:
                    dbcrud.recompute_and_update_batch_kpis_by_name(db, bank_code=bank_code, batch_name=batch_name)
    except Exception:
        pass

    resp = Response(content=content, media_type="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = "attachment; filename=cheques.csv"
    return resp


# Helper: check allowed image extensions
def _allowed_image(name: str) -> bool:
    name_l = name.lower()
    return any(name_l.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"))

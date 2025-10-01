from __future__ import annotations

import os
import random
import string
from datetime import datetime, timezone, date
from typing import Any, Dict, Tuple, Optional

from app.persistence.audit import write_audit_json
from app.services.pipeline_run import run_pipeline_on_image
from app.utils.profiling import Profiler, set_current_profiler, reset_current_profiler
from app.services.routing import decide_route
from app.services.batches import cairo_today, format_batch_name
from app.db.session import db_enabled, session_scope
from app.db import crud as dbcrud
import logging
from sqlalchemy.exc import IntegrityError
from contextlib import nullcontext
import time


def _gen_file_id(ext: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{ts}_{suffix}{ext}"


def save_upload_and_process(
    *,
    upload_dir: str,
    audit_root: str,
    bank: str,
    file_bytes: bytes,
    original_filename: str,
    correlation_id: str | None,
    public_base: str,
    # Optional DB batch override to group many files into one batch
    db_batch_name: Optional[str] = None,
    db_batch_date: Optional[date] = None,
    db_seq: Optional[int] = None,
    index_in_batch: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Save the uploaded file, create a minimal ReviewItem, and write audit JSON.

    Returns (file_id, review_item_dict)
    """
    os.makedirs(os.path.join(upload_dir, bank), exist_ok=True)
    name_lower = (original_filename or "upload").lower()
    ext = ".jpg"
    for e in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
        if name_lower.endswith(e):
            ext = e
            break
    file_id = _gen_file_id(ext)
    file_path = os.path.join(upload_dir, bank, file_id)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Optional profiler per request
    profiler_token = None
    prof = Profiler.from_env()
    if prof is not None:
        prof.add_meta(bank=bank, original_filename=original_filename)
        profiler_token = set_current_profiler(prof)

    # Run the real OCR + locator + ROI OCR pipeline and time it
    t0 = time.perf_counter()
    # Do not force langs; let pipeline decide based on MUTE_NAME (env)
    fields = run_pipeline_on_image(file_path, bank=bank, template_id="auto", langs=None, min_conf=0.3)
    # Decide routing based on computed field confidences
    rd = decide_route(fields)
    decision = {
        "decision": rd.decision,
        "stp": rd.stp,
        "overall_conf": float(rd.overall_conf),
        "low_conf_fields": list(rd.low_conf_fields),
        "reasons": list(rd.reasons),
    }

    os.makedirs(os.path.join(audit_root, bank), exist_ok=True)
    write_audit_json(
        bank=bank,
        file_id=os.path.basename(file_id),
        decision=decision,
        per_field=fields,
        out_dir=audit_root,
        correlation_id=correlation_id,
        extra_meta={"source": "upload"},
    )

    # Build absolute image URL using the given public base
    public_base = public_base.rstrip("/")
    image_url = f"{public_base}/files/{bank}/{os.path.basename(file_id)}"

    review_item = {
        "bank": bank,
        "file": os.path.basename(file_id),
        "decision": decision,
        "fields": fields,
        "imageUrl": image_url,
    }

    # Best-effort DB persistence when enabled
    try:
        if db_enabled():
            span = (prof.span("db_persist") if prof is not None else nullcontext())
            with span:
                with session_scope() as db:
                    # If override provided, reuse that batch; else compute default one-per-call
                    if db_batch_name:
                        d = db_batch_date or cairo_today()
                        s = db_seq or dbcrud.get_max_seq_for_bank_date(db, bank_code=bank, d=d) + 1
                        batch_name = db_batch_name
                    else:
                        d = cairo_today()
                        s = dbcrud.get_max_seq_for_bank_date(db, bank_code=bank, d=d) + 1
                        batch_name = format_batch_name(d, bank, s)
                    # ensure bank exists to satisfy FK
                    dbcrud.ensure_bank_exists(db, code=bank, name=bank)
                    batch = dbcrud.get_batch_by_name(db, bank_code=bank, name=batch_name)
                    if batch is None:
                        try:
                            batch = dbcrud.create_batch(db, bank_code=bank, name=batch_name, batch_date=d, seq=s)
                        except IntegrityError:
                            # Another concurrent request created the same batch; fetch it
                            db.rollback()
                            batch = dbcrud.get_batch_by_name(db, bank_code=bank, name=batch_name)
                            if batch is None:
                                raise
                    # Persist cheque and fields
                    # Compute processing time (ms) from pipeline run
                    processing_ms = int((time.perf_counter() - t0) * 1000)
                    dbcrud.create_cheque_with_fields(
                        db,
                        batch=batch,
                        bank_code=bank,
                        file_id=os.path.basename(file_id),
                        original_filename=original_filename,
                        image_path=file_path,
                        decision=decision,
                        processed_at=datetime.now(timezone.utc),
                        index_in_batch=index_in_batch,
                        fields=fields,
                        processing_ms=processing_ms,
                    )
    except Exception as e:
        # DB write is best-effort and should not break the upload flow
        logging.getLogger(__name__).exception("DB persistence error during save_upload_and_process: %s", e)

    # Dump profiling info (best-effort)
    try:
        if prof is not None:
            try:
                prof.add_meta(file_id=os.path.basename(file_id))
            except Exception:
                pass
            # Use AUDIT_ROOT for bank folder consistency; fall back to default
            prof.dump_to_file(out_dir=None, bank=bank, file_id=os.path.basename(file_id))
            prof.log_summary()
    except Exception:
        pass
    finally:
        reset_current_profiler(profiler_token)

    return os.path.basename(file_id), review_item

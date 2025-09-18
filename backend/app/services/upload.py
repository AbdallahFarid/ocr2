from __future__ import annotations

import os
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from app.persistence.audit import write_audit_json
from app.services.pipeline_run import run_pipeline_on_image
from app.services.routing import decide_route


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

    # Run the real OCR + locator + ROI OCR pipeline
    fields = run_pipeline_on_image(file_path, bank=bank, template_id="auto", langs=["en", "ar"], min_conf=0.3)
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

    return os.path.basename(file_id), review_item

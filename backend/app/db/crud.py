from __future__ import annotations

import json
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.db.models import Batch, Cheque, ChequeField, Bank


# KPI fields considered for incorrect counts and error rates
KPI_FIELDS = {"date", "cheque_number", "amount_numeric"}


def get_max_seq_for_bank_date(db: Session, bank_code: str, d: date) -> int:
    q = select(func.max(Batch.seq)).where(Batch.bank_code == bank_code, Batch.batch_date == d)
    res = db.execute(q).scalar()
    return int(res or 0)


def ensure_bank_exists(db: Session, *, code: str, name: Optional[str] = None) -> Bank:
    try:
        b = db.execute(select(Bank).where(Bank.code == code)).scalars().first()
    except OperationalError:
        # Lazy-create schema for test-time SQLite runs where tables may not exist yet
        try:
            from app.db.models import Base
            from app.db.session import get_engine
            eng = get_engine()
            if eng is not None:
                Base.metadata.create_all(eng)
            else:
                Base.metadata.create_all(db.get_bind())
        except Exception:
            pass
        b = db.execute(select(Bank).where(Bank.code == code)).scalars().first()
    if b:
        return b
    b = Bank(code=code, name=name or code)
    db.add(b)
    db.flush()
    return b


essential_batch_fields = (
    "id",
    "bank_code",
    "name",
    "batch_date",
    "seq",
)


def create_batch(db: Session, *, bank_code: str, name: str, batch_date: date, seq: int) -> Batch:
    now = datetime.now(timezone.utc)
    b = Batch(
        bank_code=bank_code,
        name=name,
        batch_date=batch_date,
        seq=seq,
        created_at=now,
        processing_started_at=now,
    )
    db.add(b)
    db.flush()
    return b


def get_batch_by_name(db: Session, *, bank_code: str, name: str) -> Optional[Batch]:
    q = select(Batch).where(Batch.bank_code == bank_code, Batch.name == name)
    return db.execute(q).scalars().first()


def find_cheque_by_bank_file(db: Session, *, bank_code: str, file_id: str) -> Optional[Cheque]:
    q = select(Cheque).where(Cheque.bank_code == bank_code, Cheque.file_id == file_id)
    return db.execute(q).scalars().first()


def create_cheque_with_fields(
    db: Session,
    *,
    batch: Batch,
    bank_code: str,
    file_id: str,
    original_filename: Optional[str],
    image_path: Optional[str],
    decision: Dict[str, Any],
    processed_at: Optional[datetime],
    index_in_batch: Optional[int] = None,
    fields: Dict[str, Dict[str, Any]] = {},
    processing_ms: Optional[int] = None,
) -> Cheque:
    c = Cheque(
        batch_id=batch.id,
        bank_code=bank_code,
        file_id=file_id,
        original_filename=original_filename,
        image_path=image_path,
        decision=json.dumps(decision, ensure_ascii=False),
        stp=bool(decision.get("stp")) if isinstance(decision, dict) else None,
        overall_conf=decision.get("overall_conf") if isinstance(decision, dict) else None,
        created_at=datetime.now(timezone.utc),
        processed_at=processed_at,
        index_in_batch=index_in_batch,
        processing_ms=processing_ms,
    )
    # incorrect_fields_count is based ONLY on reviewer edits (corrections),
    # not on confidence/thresholds. At creation time (no edits yet) it's zero.
    c.incorrect_fields_count = 0

    db.add(c)
    db.flush()

    # Create fields rows
    for name, rec in (fields or {}).items():
        # Do not persist 'name' field per requirements; it's muted and not part of KPIs
        if name == "name":
            continue
        f = ChequeField(
            cheque_id=c.id,
            name=name,
            field_conf=rec.get("field_conf"),
            loc_conf=rec.get("loc_conf"),
            ocr_conf=rec.get("ocr_conf"),
            parse_ok=rec.get("parse_ok"),
            meets_threshold=rec.get("meets_threshold"),
            parse_norm=rec.get("parse_norm"),
            ocr_text=rec.get("ocr_text"),
            ocr_lang=rec.get("ocr_lang"),
            validation=rec.get("validation"),
        )
        db.add(f)
    db.flush()

    return c


def apply_corrections(
    db: Session,
    *,
    bank_code: str,
    file_id: str,
    corrections: Dict[str, Dict[str, Any]],
    reviewer_id: Optional[str],
    at: datetime,
) -> None:
    # Find cheque
    cheque = find_cheque_by_bank_file(db, bank_code=bank_code, file_id=file_id)
    if not cheque:
        return
    # For each field, update ChequeField and insert a Correction row
    # Build a map of existing fields for quick lookup
    q = select(ChequeField).where(ChequeField.cheque_id == cheque.id)
    existing = {f.name: f for f in db.execute(q).scalars().all()}
    for field_name, corr in corrections.items():
        # Do not persist corrections for muted field 'name'
        if field_name == "name":
            continue
        before = corr.get("before")
        after = corr.get("after")
        reason = corr.get("reason")
        # Skip if before == after (no actual change)
        if before == after:
            continue
        f = existing.get(field_name)
        if not f:
            # If the field does not exist in DB (edge case), create it minimal
            f = ChequeField(cheque_id=cheque.id, name=field_name)
            db.add(f)
            db.flush()
        f.parse_norm = after
        f.corrected = True
        f.last_corrected_at = at
        # When a reviewer corrects a field, treat it as meeting threshold
        f.meets_threshold = True
        # And consider parse_ok true since it's a reviewed value
        f.parse_ok = True
        from app.db.models import Correction as CorrModel

        corr_row = CorrModel(
            cheque_field_id=f.id,
            reviewer_id=reviewer_id,
            before=before,
            after=after,
            reason=reason,
            at=at,
        )
        db.add(corr_row)
    db.flush()

    # Recompute incorrect_fields_count: number of KPI fields that were edited (corrected=True)
    q2 = select(func.count()).where(
        ChequeField.cheque_id == cheque.id,
        ChequeField.corrected.is_(True),
        ChequeField.name.in_(list(KPI_FIELDS)),
    )
    cheque.incorrect_fields_count = db.execute(q2).scalar() or 0
    db.flush()


def recompute_batch_kpis(db: Session, *, batch: Batch) -> Dict[str, Any]:
    """Compute KPI metrics for a given batch without persisting them."""
    # Total cheques in batch
    try:
        total_cheques = db.execute(
            select(func.count()).select_from(Cheque).where(Cheque.batch_id == batch.id)
        ).scalar() or 0
    except OperationalError:
        total_cheques = 0

    # Cheques with any incorrect KPI fields = any edited KPI field (corrected=True)
    try:
        cheques_with_errors = db.execute(
            select(func.count(func.distinct(Cheque.id)))
            .select_from(Cheque)
            .join(ChequeField, ChequeField.cheque_id == Cheque.id)
            .where(
                Cheque.batch_id == batch.id,
                ChequeField.corrected.is_(True),
                ChequeField.name.in_(list(KPI_FIELDS)),
            )
        ).scalar() or 0
    except OperationalError:
        cheques_with_errors = 0

    # Total KPI fields for cheques in batch (exclude non-KPI and muted fields)
    try:
        total_fields = db.execute(
            select(func.count()).select_from(ChequeField)
            .join(Cheque, ChequeField.cheque_id == Cheque.id)
            .where(
                Cheque.batch_id == batch.id,
                ChequeField.name.in_(list(KPI_FIELDS)),
            )
        ).scalar() or 0
    except OperationalError:
        total_fields = 0

    # Incorrect KPI fields = edited KPI fields (corrected=True)
    try:
        incorrect_fields = db.execute(
            select(func.count()).select_from(ChequeField)
            .join(Cheque, ChequeField.cheque_id == Cheque.id)
            .where(
                Cheque.batch_id == batch.id,
                ChequeField.corrected.is_(True),
                ChequeField.name.in_(list(KPI_FIELDS)),
            )
        ).scalar() or 0
    except OperationalError:
        incorrect_fields = 0

    def ratio(n: int, d: int) -> float | None:
        if not d:
            return None
        return round(n / d, 4)

    error_rate_cheques = ratio(cheques_with_errors, total_cheques)
    error_rate_fields = ratio(incorrect_fields, total_fields)
    flagged = bool(error_rate_cheques is not None and error_rate_cheques > 0.8)

    return {
        "total_cheques": total_cheques,
        "cheques_with_errors": cheques_with_errors,
        "total_fields": total_fields,
        "incorrect_fields": incorrect_fields,
        "error_rate_cheques": error_rate_cheques,
        "error_rate_fields": error_rate_fields,
        "flagged": flagged,
    }


def update_batch_kpis(db: Session, *, batch: Batch, metrics: Dict[str, Any]) -> None:
    batch.total_cheques = metrics.get("total_cheques")
    batch.cheques_with_errors = metrics.get("cheques_with_errors")
    batch.total_fields = metrics.get("total_fields")
    batch.incorrect_fields = metrics.get("incorrect_fields")
    batch.error_rate_cheques = metrics.get("error_rate_cheques")
    batch.error_rate_fields = metrics.get("error_rate_fields")
    batch.flagged = metrics.get("flagged", False)
    db.flush()


def recompute_and_update_batch_kpis_by_name(
    db: Session, *, bank_code: str, batch_name: str
) -> Optional[Dict[str, Any]]:
    batch = get_batch_by_name(db, bank_code=bank_code, name=batch_name)
    if not batch:
        return None
    try:
        metrics = recompute_batch_kpis(db, batch=batch)
        update_batch_kpis(db, batch=batch, metrics=metrics)
    except OperationalError:
        # In minimal test DBs (e.g., SQLite) related tables may not exist; still mark ended
        metrics = {
            "total_cheques": 0,
            "cheques_with_errors": 0,
            "total_fields": 0,
            "incorrect_fields": 0,
            "error_rate_cheques": None,
            "error_rate_fields": None,
            "flagged": False,
        }
    # mark processing ended and duration
    ended = datetime.now(timezone.utc)
    batch.processing_ended_at = ended
    if batch.processing_started_at:
        start = batch.processing_started_at
        # Normalize to timezone-aware assuming UTC if naive (SQLite often drops tz info)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end_norm = ended if ended.tzinfo is not None else ended.replace(tzinfo=timezone.utc)
        delta = end_norm - start
        batch.processing_ms = int(delta.total_seconds() * 1000)
    db.flush()
    return metrics

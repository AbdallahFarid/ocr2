from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, and_, func

from app.constants.banks import ALLOWED_BANKS
from app.db.session import session_scope, db_enabled
from app.db.models import Batch, Cheque

router = APIRouter(prefix="/batches", tags=["batches"])


def _parse_iso_date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


@router.get("")
async def list_batches(
    bank: str = Query(..., description="Bank code"),
    from_: Optional[str] = Query(None, alias="from", description="Start date YYYY-MM-DD inclusive"),
    to: Optional[str] = Query(None, alias="to", description="End date YYYY-MM-DD inclusive"),
    flagged: Optional[bool] = Query(None, description="Filter by flagged batches"),
) -> List[Dict[str, Any]]:
    if not db_enabled():
        raise HTTPException(status_code=503, detail="DB not enabled")
    bank = bank.strip().upper()
    if bank not in ALLOWED_BANKS:
        raise HTTPException(status_code=400, detail="Unsupported bank")

    d_from = _parse_iso_date(from_)
    d_to = _parse_iso_date(to)

    with session_scope() as db:
        conds = [Batch.bank_code == bank]
        if d_from:
            conds.append(Batch.batch_date >= d_from)
        if d_to:
            conds.append(Batch.batch_date <= d_to)
        if flagged is not None:
            conds.append(Batch.flagged.is_(flagged))
        q = (
            select(Batch)
            .where(and_(*conds))
            .order_by(Batch.batch_date.desc(), Batch.seq.desc())
        )
        rows = db.execute(q).scalars().all()
        out: List[Dict[str, Any]] = []
        for b in rows:
            out.append({
                "bank": b.bank_code,
                "name": b.name,
                "batch_date": b.batch_date.isoformat(),
                "seq": b.seq,
                "flagged": bool(b.flagged),
                "status": b.status,
                "processing_started_at": b.processing_started_at.isoformat() if b.processing_started_at else None,
                "processing_ended_at": b.processing_ended_at.isoformat() if b.processing_ended_at else None,
                "processing_ms": b.processing_ms,
                "total_cheques": b.total_cheques,
                "cheques_with_errors": b.cheques_with_errors,
                "total_fields": b.total_fields,
                "incorrect_fields": b.incorrect_fields,
                "error_rate_cheques": float(b.error_rate_cheques) if b.error_rate_cheques is not None else None,
                "error_rate_fields": float(b.error_rate_fields) if b.error_rate_fields is not None else None,
            })
        return out


@router.get("/{bank}/{batch_name}")
async def get_batch_detail(bank: str, batch_name: str) -> Dict[str, Any]:
    if not db_enabled():
        raise HTTPException(status_code=503, detail="DB not enabled")
    bank = bank.strip().upper()
    if bank not in ALLOWED_BANKS:
        raise HTTPException(status_code=400, detail="Unsupported bank")
    with session_scope() as db:
        b = db.execute(
            select(Batch).where(Batch.bank_code == bank, Batch.name == batch_name)
        ).scalars().first()
        if not b:
            raise HTTPException(status_code=404, detail="Batch not found")
        # Cheques for the batch
        cheques = db.execute(
            select(Cheque).where(Cheque.batch_id == b.id).order_by(Cheque.index_in_batch.asc())
        ).scalars().all()
        items: List[Dict[str, Any]] = []
        for c in cheques:
            items.append({
                "file": c.file_id,
                "incorrect_fields_count": c.incorrect_fields_count,
                "decision": c.decision,
                "stp": c.stp,
                "overall_conf": float(c.overall_conf) if c.overall_conf is not None else None,
                "index_in_batch": c.index_in_batch,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })
        return {
            "bank": b.bank_code,
            "name": b.name,
            "batch_date": b.batch_date.isoformat(),
            "seq": b.seq,
            "flagged": bool(b.flagged),
            "status": b.status,
            "kpis": {
                "total_cheques": b.total_cheques,
                "cheques_with_errors": b.cheques_with_errors,
                "total_fields": b.total_fields,
                "incorrect_fields": b.incorrect_fields,
                "error_rate_cheques": float(b.error_rate_cheques) if b.error_rate_cheques is not None else None,
                "error_rate_fields": float(b.error_rate_fields) if b.error_rate_fields is not None else None,
            },
            "cheques": items,
        }

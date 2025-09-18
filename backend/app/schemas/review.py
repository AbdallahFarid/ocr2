from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CorrectionFieldUpdate(BaseModel):
    value: str = Field(..., description="New normalized value for the field")
    reason: Optional[str] = Field(None, description="Optional reason/comment for the correction")


class CorrectionPayload(BaseModel):
    reviewer_id: str = Field(..., description="Reviewer identifier")
    updates: Dict[str, CorrectionFieldUpdate] = Field(
        ..., description="Mapping field name -> correction"
    )
    correlation_id: Optional[str] = Field(None, description="Optional correlation id for run/session")


class CorrectionRecord(BaseModel):
    reviewer_id: str
    field: str
    before: Optional[str]
    after: str
    reason: Optional[str] = None
    at: str  # ISO8601


class CorrectionResult(BaseModel):
    ok: bool
    updated_fields: List[str]
    corrections_appended: List[CorrectionRecord]


class FieldRecord(BaseModel):
    field_conf: Optional[float] = None
    loc_conf: Optional[float] = None
    ocr_conf: Optional[float] = None
    parse_ok: Optional[bool] = None
    parse_norm: Optional[str] = None
    ocr_text: Optional[str] = None
    ocr_lang: Optional[str] = None
    meets_threshold: Optional[bool] = None
    validation: Optional[dict] = None


class Decision(BaseModel):
    decision: str
    stp: bool
    overall_conf: float
    low_conf_fields: List[str]
    reasons: List[str]


class ReviewItem(BaseModel):
    bank: str
    file: str
    decision: Decision
    fields: Dict[str, FieldRecord]
    imageUrl: Optional[str] = None

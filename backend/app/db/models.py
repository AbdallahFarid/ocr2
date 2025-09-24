from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Bank(Base):
    __tablename__ = "banks"
    code = Column(String(32), primary_key=True)
    name = Column(String(128))


class Batch(Base):
    __tablename__ = "batches"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_code = Column(String(32), ForeignKey("banks.code", ondelete="RESTRICT"), nullable=False)
    name = Column(String(64), nullable=False)
    batch_date = Column(Date, nullable=False)
    seq = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending_review")
    flagged = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processing_started_at = Column(DateTime(timezone=True))
    processing_ended_at = Column(DateTime(timezone=True))
    processing_ms = Column(Integer)
    total_cheques = Column(Integer)
    cheques_with_errors = Column(Integer)
    total_fields = Column(Integer)
    incorrect_fields = Column(Integer)
    error_rate_cheques = Column(Numeric(6, 4))
    error_rate_fields = Column(Numeric(6, 4))

    __table_args__ = (
        UniqueConstraint("bank_code", "batch_date", "seq", name="uq_batches_bank_date_seq"),
        Index("ix_batches_bank_created", "bank_code", "created_at"),
        Index("ix_batches_flagged", "flagged"),
        Index("ix_batches_status", "status"),
    )

    bank = relationship("Bank")
    cheques = relationship("Cheque", back_populates="batch", cascade="all, delete-orphan")


class Cheque(Base):
    __tablename__ = "cheques"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False)
    bank_code = Column(String(32), ForeignKey("banks.code", ondelete="RESTRICT"), nullable=False)
    file_id = Column(String(64), nullable=False)
    original_filename = Column(String(256))
    image_path = Column(String(512))
    decision = Column(Text)
    stp = Column(Boolean)
    overall_conf = Column(Numeric(5, 3))
    processing_ms = Column(Integer)
    incorrect_fields_count = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processed_at = Column(DateTime(timezone=True))
    index_in_batch = Column(Integer)

    __table_args__ = (
        UniqueConstraint("bank_code", "file_id", name="uq_cheques_bank_file"),
    )

    batch = relationship("Batch", back_populates="cheques")
    fields = relationship("ChequeField", back_populates="cheque", cascade="all, delete-orphan")


class ChequeField(Base):
    __tablename__ = "cheque_fields"
    id = Column(Integer, primary_key=True)
    cheque_id = Column(UUID(as_uuid=True), ForeignKey("cheques.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(64), nullable=False)
    field_conf = Column(Numeric(5, 3))
    loc_conf = Column(Numeric(5, 3))
    ocr_conf = Column(Numeric(5, 3))
    parse_ok = Column(Boolean)
    meets_threshold = Column(Boolean)
    parse_norm = Column(Text)
    ocr_text = Column(Text)
    ocr_lang = Column(String(8))
    validation = Column(JSONB)
    corrected = Column(Boolean, nullable=False, default=False)
    last_corrected_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_cheque_fields_cheque_name", "cheque_id", "name"),
    )

    cheque = relationship("Cheque", back_populates="fields")
    corrections = relationship("Correction", back_populates="field", cascade="all, delete-orphan")


class Correction(Base):
    __tablename__ = "corrections"
    id = Column(Integer, primary_key=True)
    cheque_field_id = Column(Integer, ForeignKey("cheque_fields.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(String(64))
    before = Column(Text)
    after = Column(Text)
    reason = Column(Text)
    at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_corrections_at", "at"),
    )

    field = relationship("ChequeField", back_populates="corrections")

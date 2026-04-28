"""
SQLAlchemy ORM model for the 'decisions' table.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, String, DateTime, DECIMAL, Boolean, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Decision(Base):
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_id = Column(UUID(as_uuid=True), nullable=False)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    system_status = Column(String(20), default="OK")
    requires_manual_review = Column(Boolean, default=False)
    decision_reason = Column(String(50), default="RISK")
    data_validity = Column(String(20), default="VALID")
    ml_execution_mode = Column(String(20), default="FULL")
    risk_level = Column(String(20), default="SAFE")
    probability = Column(DECIMAL(5, 4), default=0.0)
    confidence_score = Column(DECIMAL(5, 4), default=0.0)
    trace = Column(String(255), default="")
    explanation = Column(String(255), default="")
    failure_modes = Column(JSONB)
    is_safe_for_automation = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    decision_timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Decision(id={self.id}, evaluation_id={self.evaluation_id}, risk_level={self.risk_level})>"

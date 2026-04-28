"""
SQLAlchemy ORM model for the 'pipeline_runs' table.
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

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.id"), nullable=True)
    execution_mode = Column(String(20), default="production")
    origin = Column(String(100))
    destination = Column(String(100))
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))
    execution_time_ms = Column(DECIMAL(12, 3))
    system_status = Column(String(20))
    risk_level = Column(String(20))
    confidence_score = Column(DECIMAL(5, 4))
    final_decision = Column(JSONB)
    error_stage = Column(String(50))
    error_message = Column(String(255))
    is_emergency_output = Column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<PipelineRun(id={self.id}, snapshot_id={self.snapshot_id}, started_at={self.started_at})>"

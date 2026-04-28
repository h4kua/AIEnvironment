"""
SQLAlchemy ORM model for the 'snapshots' table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column, String, DateTime, DECIMAL, JSON, VARCHAR
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_hash = Column(String(64), unique=True, nullable=False)
    fetched_at_utc = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    location = Column(String(100))
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    openweather = Column(JSONB)
    poskobanjir = Column(JSONB)
    bmkg_alerts = Column(JSONB)
    data_freshness_minutes = Column(DECIMAL(8, 2))
    snapshot_completeness = Column(DECIMAL(5, 4))
    processing_status = Column(String(20), default="pending")

    def __repr__(self) -> str:
        return f"<Snapshot(id={self.id}, hash={self.snapshot_hash}, fetched_at_utc={self.fetched_at_utc})>"

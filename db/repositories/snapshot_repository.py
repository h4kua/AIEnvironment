"""
Snapshot repository - CRUD operations for raw input data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Snapshot


class SnapshotRepository:
    """Repository for snapshot CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        fetched_at_utc: datetime,
        openweather: dict | None = None,
        poskobanjir: list | None = None,
        bmkg_alerts: list | None = None,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> Snapshot:
        """Create a new snapshot."""
        # Generate hash for deduplication
        snapshot_data = {
            "fetched_at_utc": fetched_at_utc.isoformat() if fetched_at_utc else None,
            "openweather": openweather,
            "poskobanjir": poskobanjir,
            "bmkg_alerts": bmkg_alerts,
        }
        snapshot_hash = hashlib.sha256(
            json.dumps(snapshot_data, sort_keys=True).encode()
        ).hexdigest()
        
        snapshot = Snapshot(
            snapshot_hash=snapshot_hash,
            fetched_at_utc=fetched_at_utc,
            openweather=openweather,
            poskobanjir=poskobanjir,
            bmkg_alerts=bmkg_alerts,
            location=location,
            latitude=latitude,
            longitude=longitude,
            processing_status="pending",
        )
        
        self.session.add(snapshot)
        self.session.flush()
        return snapshot
    
    def get_by_id(self, snapshot_id: UUID) -> Optional[Snapshot]:
        """Get snapshot by ID."""
        return self.session.get(Snapshot, snapshot_id)
    
    def get_by_hash(self, snapshot_hash: str) -> Optional[Snapshot]:
        """Get snapshot by hash (for deduplication)."""
        return (
            self.session.query(Snapshot)
            .filter(Snapshot.snapshot_hash == snapshot_hash)
            .first()
        )
    
    def get_recent(self, limit: int = 100) -> list[Snapshot]:
        """Get recent snapshots."""
        return (
            self.session.query(Snapshot)
            .order_by(Snapshot.fetched_at_utc.desc())
            .limit(limit)
            .all()
        )
    
    def update_status(
        self,
        snapshot_id: UUID,
        status: str,
        data_freshness_minutes: float | None = None,
        snapshot_completeness: float | None = None,
    ) -> Snapshot:
        """Update snapshot processing status."""
        snapshot = self.get_by_id(snapshot_id)
        if snapshot:
            snapshot.processing_status = status
            if data_freshness_minutes is not None:
                snapshot.data_freshness_minutes = data_freshness_minutes
            if snapshot_completeness is not None:
                snapshot.snapshot_completeness = snapshot_completeness
            self.session.flush()
        return snapshot
    
    def delete(self, snapshot_id: UUID) -> bool:
        """Delete a snapshot."""
        snapshot = self.get_by_id(snapshot_id)
        if snapshot:
            self.session.delete(snapshot)
            self.session.flush()
            return True
        return False
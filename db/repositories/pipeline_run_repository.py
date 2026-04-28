"""
Pipeline run repository - CRUD operations for pipeline execution logs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PipelineRun


class PipelineRunRepository:
    """Repository for pipeline run CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        snapshot_id: UUID | None = None,
        execution_mode: str = "production",
        origin: str | None = None,
        destination: str | None = None,
    ) -> PipelineRun:
        """Create a new pipeline run."""
        pipeline_run = PipelineRun(
            snapshot_id=snapshot_id,
            execution_mode=execution_mode,
            origin=origin,
            destination=destination,
            started_at=datetime.now(timezone.utc),
        )
        
        self.session.add(pipeline_run)
        self.session.flush()
        return pipeline_run
    
    def get_by_id(self, run_id: UUID) -> Optional[PipelineRun]:
        """Get pipeline run by ID."""
        return self.session.get(PipelineRun, run_id)
    
    def update_completion(
        self,
        run_id: UUID,
        system_status: str | None = None,
        risk_level: str | None = None,
        confidence_score: float | None = None,
        final_decision: dict | None = None,
        error_stage: str | None = None,
        error_message: str | None = None,
        is_emergency_output: bool = False,
    ) -> PipelineRun:
        """Update pipeline run with completion data."""
        run = self.get_by_id(run_id)
        if run:
            run.completed_at = datetime.now(timezone.utc)
            run.execution_time_ms = (
                (run.completed_at - run.started_at).total_seconds() * 1000
            )
            
            if system_status:
                run.system_status = system_status
            if risk_level:
                run.risk_level = risk_level
            if confidence_score is not None:
                run.confidence_score = confidence_score
            if final_decision:
                run.final_decision = final_decision
            if error_stage:
                run.error_stage = error_stage
            if error_message:
                run.error_message = error_message
            run.is_emergency_output = is_emergency_output
            
            self.session.flush()
        return run
    
    def get_recent(self, limit: int = 100) -> list[PipelineRun]:
        """Get recent pipeline runs."""
        return (
            self.session.query(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
            .all()
        )
    
    def get_by_status(self, status: str, limit: int = 100) -> list[PipelineRun]:
        """Get pipeline runs by status."""
        return (
            self.session.query(PipelineRun)
            .filter(PipelineRun.system_status == status)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
            .all()
        )


# Import timezone for datetime
from datetime import timezone
"""
Decision repository - CRUD operations for final decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from db.models import Decision


class DecisionRepository:
    """Repository for decision CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        evaluation_id: UUID,
        pipeline_run_id: UUID | None = None,
        system_status: str = "OK",
        requires_manual_review: bool = False,
        decision_reason: str = "RISK",
        data_validity: str = "VALID",
        ml_execution_mode: str = "FULL",
        risk_level: str = "SAFE",
        probability: float = 0.0,
        confidence_score: float = 0.0,
        trace: str = "",
        explanation: str = "",
        failure_modes: list | None = None,
        is_safe_for_automation: bool = True,
    ) -> Decision:
        """Create a new decision."""
        decision = Decision(
            evaluation_id=evaluation_id,
            pipeline_run_id=pipeline_run_id,
            system_status=system_status,
            requires_manual_review=requires_manual_review,
            decision_reason=decision_reason,
            data_validity=data_validity,
            ml_execution_mode=ml_execution_mode,
            risk_level=risk_level,
            probability=probability,
            confidence_score=confidence_score,
            trace=trace,
            explanation=explanation,
            failure_modes=failure_modes or [],
            is_safe_for_automation=is_safe_for_automation,
            created_at=datetime.now(timezone.utc),
            decision_timestamp=datetime.now(timezone.utc),
        )
        
        self.session.add(decision)
        self.session.flush()
        return decision
    
    def get_by_id(self, decision_id: UUID) -> Optional[Decision]:
        """Get decision by ID."""
        return self.session.get(Decision, decision_id)
    
    def get_by_evaluation(self, evaluation_id: UUID) -> Optional[Decision]:
        """Get decision by evaluation ID."""
        return (
            self.session.query(Decision)
            .filter(Decision.evaluation_id == evaluation_id)
            .first()
        )
    
    def get_recent(self, limit: int = 100) -> list[Decision]:
        """Get recent decisions."""
        return (
            self.session.query(Decision)
            .order_by(Decision.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def get_by_risk_level(self, risk_level: str, limit: int = 100) -> list[Decision]:
        """Get decisions by risk level."""
        return (
            self.session.query(Decision)
            .filter(Decision.risk_level == risk_level)
            .order_by(Decision.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def update(
        self,
        decision_id: UUID,
        **kwargs,
    ) -> Decision:
        """Update decision fields."""
        decision = self.get_by_id(decision_id)
        if decision:
            for key, value in kwargs.items():
                if hasattr(decision, key):
                    setattr(decision, key, value)
            self.session.flush()
        return decision
"""
Transactional psycopg2 writer for the multi-stage AI pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional
from uuid import UUID

from psycopg2.extras import Json, register_uuid
from psycopg2.extensions import connection as PgConnection

from db.psycopg2_connection import (
    Psycopg2ConnectionConfig,
    get_psycopg2_connection,
)

register_uuid()

ALLOWED_RISK_LEVELS = frozenset({"SAFE", "WARNING", "DANGER"})


@dataclass(frozen=True)
class PipelineRunConfig:
    """Optional metadata for the pipeline_runs row."""

    execution_mode: str = "production"
    origin: Optional[str] = None
    destination: Optional[str] = None
    api_version: Optional[str] = None
    pipeline_version: Optional[str] = None


@dataclass(frozen=True)
class PerceptionPayload:
    data_freshness_minutes: float
    snapshot_completeness: float
    signal_presence: Mapping[str, Any]


@dataclass(frozen=True)
class ReasoningPayload:
    probability: float
    confidence_score: float
    model_variant: Optional[str] = None


@dataclass(frozen=True)
class EvaluationPayload:
    system_status: str
    risk_level: str
    probability: float
    confidence_score: float
    requires_manual_review: bool


@dataclass(frozen=True)
class DecisionPayload:
    system_status: str
    requires_manual_review: bool
    decision_reason: str
    data_validity: str
    ml_execution_mode: str
    risk_level: str
    probability: float
    confidence_score: float
    is_safe_for_automation: bool


@dataclass(frozen=True)
class PipelineExecutionResult:
    """All generated primary keys from a successful pipeline execution."""

    snapshot_id: UUID
    pipeline_run_id: UUID
    perception_id: UUID
    reasoning_id: UUID
    evaluation_id: UUID
    decision_id: UUID

    def as_dict(self) -> Dict[str, str]:
        """Serialize UUID values for logging or API responses."""
        return {
            "snapshot_id": str(self.snapshot_id),
            "pipeline_run_id": str(self.pipeline_run_id),
            "perception_id": str(self.perception_id),
            "reasoning_id": str(self.reasoning_id),
            "evaluation_id": str(self.evaluation_id),
            "decision_id": str(self.decision_id),
        }


def execute_pipeline(
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
    perception: PerceptionPayload,
    reasoning: ReasoningPayload,
    evaluation: EvaluationPayload,
    decision: DecisionPayload,
    pipeline_run: Optional[PipelineRunConfig] = None,
    connection: Optional[PgConnection] = None,
    db_config: Optional[Psycopg2ConnectionConfig] = None,
) -> PipelineExecutionResult:
    """
    Persist one complete pipeline execution in a single database transaction.

    The stage order is mandatory and enforced:
    snapshot -> pipeline_run -> perception -> reasoning -> evaluation -> decision
    """
    _validate_risk_level(evaluation.risk_level, field_name="evaluation.risk_level")
    _validate_risk_level(decision.risk_level, field_name="decision.risk_level")

    owns_connection = connection is None
    active_connection = connection or get_psycopg2_connection(db_config)
    run_config = pipeline_run or PipelineRunConfig()
    transaction_started_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    try:
        with active_connection.cursor() as cursor:
            snapshot_id = create_snapshot(
                cursor=cursor,
                snapshot_input=snapshot_input,
                location=location,
            )
            pipeline_run_id = create_pipeline_run(
                cursor=cursor,
                snapshot_id=snapshot_id,
                pipeline_run=run_config,
            )
            perception_id = insert_perception(
                cursor=cursor,
                snapshot_id=snapshot_id,
                pipeline_run_id=pipeline_run_id,
                perception=perception,
            )
            reasoning_id = insert_reasoning(
                cursor=cursor,
                perception_id=perception_id,
                pipeline_run_id=pipeline_run_id,
                reasoning=reasoning,
            )
            evaluation_id = insert_evaluation(
                cursor=cursor,
                reasoning_id=reasoning_id,
                perception_id=perception_id,
                pipeline_run_id=pipeline_run_id,
                evaluation=evaluation,
            )
            decision_id = insert_decision(
                cursor=cursor,
                evaluation_id=evaluation_id,
                pipeline_run_id=pipeline_run_id,
                decision=decision,
            )
            _finalize_pipeline_run(
                cursor=cursor,
                pipeline_run_id=pipeline_run_id,
                decision=decision,
                run_config=run_config,
                decision_id=decision_id,
                transaction_started_at=transaction_started_at,
            )

        active_connection.commit()
        return PipelineExecutionResult(
            snapshot_id=snapshot_id,
            pipeline_run_id=pipeline_run_id,
            perception_id=perception_id,
            reasoning_id=reasoning_id,
            evaluation_id=evaluation_id,
            decision_id=decision_id,
        )
    except Exception:
        active_connection.rollback()
        raise
    finally:
        if owns_connection:
            active_connection.close()


def create_snapshot(
    cursor: Any,
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
) -> UUID:
    """Insert one row into snapshots and return the generated ID."""
    snapshot_hash = _compute_snapshot_hash(snapshot_input)
    fetched_at_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

    cursor.execute(
        """
        INSERT INTO snapshots (
            snapshot_hash,
            fetched_at_utc,
            location,
            openweather,
            poskobanjir,
            bmkg_alerts
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot_hash,
            fetched_at_utc,
            location,
            _to_jsonb(snapshot_input.get("openweather")),
            _to_jsonb(snapshot_input.get("poskobanjir")),
            _to_jsonb(snapshot_input.get("bmkg_alerts")),
        ),
    )
    return cursor.fetchone()[0]


def create_pipeline_run(
    cursor: Any,
    snapshot_id: UUID,
    pipeline_run: PipelineRunConfig,
) -> UUID:
    """Insert one row into pipeline_runs and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO pipeline_runs (
            snapshot_id,
            execution_mode,
            started_at,
            origin,
            destination,
            api_version,
            pipeline_version
        )
        VALUES (%s, %s, NOW(), %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot_id,
            pipeline_run.execution_mode,
            pipeline_run.origin,
            pipeline_run.destination,
            pipeline_run.api_version,
            pipeline_run.pipeline_version,
        ),
    )
    return cursor.fetchone()[0]


def insert_perception(
    cursor: Any,
    snapshot_id: UUID,
    pipeline_run_id: UUID,
    perception: PerceptionPayload,
) -> UUID:
    """Insert one row into perception_results and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO perception_results (
            snapshot_id,
            pipeline_run_id,
            data_freshness_minutes,
            snapshot_completeness,
            signal_presence
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot_id,
            pipeline_run_id,
            _as_decimal(perception.data_freshness_minutes),
            _as_decimal(perception.snapshot_completeness),
            Json(dict(perception.signal_presence)),
        ),
    )
    return cursor.fetchone()[0]


def insert_reasoning(
    cursor: Any,
    perception_id: UUID,
    pipeline_run_id: UUID,
    reasoning: ReasoningPayload,
) -> UUID:
    """Insert one row into reasoning_results and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO reasoning_results (
            perception_id,
            pipeline_run_id,
            probability,
            confidence_score,
            model_variant
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            perception_id,
            pipeline_run_id,
            _as_decimal(reasoning.probability),
            _as_decimal(reasoning.confidence_score),
            reasoning.model_variant,
        ),
    )
    return cursor.fetchone()[0]


def insert_evaluation(
    cursor: Any,
    reasoning_id: UUID,
    perception_id: UUID,
    pipeline_run_id: UUID,
    evaluation: EvaluationPayload,
) -> UUID:
    """Insert one row into evaluation_results and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO evaluation_results (
            reasoning_id,
            perception_id,
            pipeline_run_id,
            system_status,
            risk_level,
            probability,
            confidence_score,
            requires_manual_review
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            reasoning_id,
            perception_id,
            pipeline_run_id,
            evaluation.system_status,
            evaluation.risk_level,
            _as_decimal(evaluation.probability),
            _as_decimal(evaluation.confidence_score),
            evaluation.requires_manual_review,
        ),
    )
    return cursor.fetchone()[0]


def insert_decision(
    cursor: Any,
    evaluation_id: UUID,
    pipeline_run_id: UUID,
    decision: DecisionPayload,
) -> UUID:
    """Insert one row into decisions and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO decisions (
            evaluation_id,
            pipeline_run_id,
            system_status,
            requires_manual_review,
            decision_reason,
            data_validity,
            ml_execution_mode,
            risk_level,
            probability,
            confidence_score,
            is_safe_for_automation,
            decision_timestamp
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            evaluation_id,
            pipeline_run_id,
            decision.system_status,
            decision.requires_manual_review,
            decision.decision_reason,
            decision.data_validity,
            decision.ml_execution_mode,
            decision.risk_level,
            _as_decimal(decision.probability),
            _as_decimal(decision.confidence_score),
            decision.is_safe_for_automation,
            datetime.utcnow().replace(tzinfo=timezone.utc),
        ),
    )
    return cursor.fetchone()[0]


def _finalize_pipeline_run(
    cursor: Any,
    pipeline_run_id: UUID,
    decision: DecisionPayload,
    run_config: PipelineRunConfig,
    decision_id: UUID,
    transaction_started_at: datetime,
) -> None:
    """
    Update the existing pipeline_runs row with completion metadata.

    This keeps the single row created in pipeline_runs aligned with the final
    decision outcome while still honoring the one-transaction requirement.
    """
    completed_at = datetime.utcnow().replace(tzinfo=timezone.utc)
    execution_time_ms = int(
        (completed_at - transaction_started_at).total_seconds() * 1000
    )
    final_decision = {
        "decision_id": str(decision_id),
        "system_status": decision.system_status,
        "requires_manual_review": decision.requires_manual_review,
        "decision_reason": decision.decision_reason,
        "data_validity": decision.data_validity,
        "ml_execution_mode": decision.ml_execution_mode,
        "risk_level": decision.risk_level,
        "probability": decision.probability,
        "confidence_score": decision.confidence_score,
        "is_safe_for_automation": decision.is_safe_for_automation,
        "pipeline_version": run_config.pipeline_version,
    }

    cursor.execute(
        """
        UPDATE pipeline_runs
        SET completed_at = %s,
            execution_time_ms = %s,
            final_decision = %s,
            system_status = %s,
            risk_level = %s,
            confidence_score = %s
        WHERE id = %s
        """,
        (
            completed_at,
            execution_time_ms,
            Json(final_decision),
            decision.system_status,
            decision.risk_level,
            _as_decimal(decision.confidence_score),
            pipeline_run_id,
        ),
    )


def _compute_snapshot_hash(snapshot_input: Mapping[str, Any]) -> str:
    normalized_snapshot = json.dumps(
        snapshot_input,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return hashlib.sha256(normalized_snapshot.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("Object of type {0} is not JSON serializable".format(type(value).__name__))


def _to_jsonb(value: Any) -> Optional[Json]:
    return None if value is None else Json(value)


def _as_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _validate_risk_level(value: str, field_name: str) -> None:
    if value not in ALLOWED_RISK_LEVELS:
        raise ValueError(
            "{0} must be one of {1}; received {2!r}".format(
                field_name,
                sorted(ALLOWED_RISK_LEVELS),
                value,
            )
        )


def result_to_dict(result: PipelineExecutionResult) -> Dict[str, str]:
    """Convenience helper for callers that prefer a plain dict response."""
    return result.as_dict()

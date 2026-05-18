"""
Example: status normalization + insert_evaluation usage.
"""

from __future__ import annotations

import logging
from uuid import UUID

from db.pipeline_writer import (
    EvaluationPayload,
    SystemStatus,
    insert_evaluation,
    normalize_status,
)


def example_normalize() -> None:
    for raw in ("READY", "success", "Running", "ERROR", "FAILED", "OK"):
        normalized = normalize_status(raw)
        assert isinstance(normalized, SystemStatus)
        logging.info("[STATUS] raw=%s normalized=%s", raw, normalized.value)

    try:
        normalize_status("UNKNOWN_STATE")
    except ValueError as exc:
        logging.warning("[STATUS] rejected: %s", exc)


def example_insert(
    cursor,
    reasoning_id: UUID,
    perception_id: UUID,
    run_id: UUID,
) -> UUID:
    payload = EvaluationPayload(
        system_status="READY",
        risk_level="SAFE",
        probability=0.42,
        confidence_score=0.91,
        requires_manual_review=False,
    )
    return insert_evaluation(
        cursor=cursor,
        reasoning_id=reasoning_id,
        perception_id=perception_id,
        pipeline_run_id=run_id,
        evaluation=payload,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    example_normalize()

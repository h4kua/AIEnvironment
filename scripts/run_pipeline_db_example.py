"""
Example usage for the transactional psycopg2 pipeline writer.
"""

from __future__ import annotations

from db.pipeline_writer import (
    DecisionPayload,
    EvaluationPayload,
    PerceptionPayload,
    PipelineRunConfig,
    ReasoningPayload,
    execute_pipeline,
    result_to_dict,
)


def main() -> None:
    snapshot_input = {
        "location": "Jakarta Selatan",
        "openweather": {
            "rain_1h_mm": 42.5,
            "humidity": 91,
            "wind_speed_mps": 5.1,
        },
        "poskobanjir": [
            {"station": "Manggarai", "status": "alert", "water_level_cm": 910},
            {"station": "Katulampa", "status": "warning", "water_level_cm": 180},
        ],
        "bmkg_alerts": [
            {"type": "heavy_rain", "severity": "high"},
            {"type": "flood_potential", "severity": "medium"},
        ],
    }

    perception = PerceptionPayload(
        data_freshness_minutes=6.5,
        snapshot_completeness=0.97,
        signal_presence={
            "rainfall_signal": True,
            "water_level_signal": True,
            "bmkg_alert_signal": True,
        },
    )
    reasoning = ReasoningPayload(
        probability=0.82,
        confidence_score=0.88,
        model_variant="xgboost-v2026.04",
    )
    evaluation = EvaluationPayload(
        system_status="READY",
        risk_level="DANGER",
        probability=0.82,
        confidence_score=0.88,
        requires_manual_review=False,
    )
    decision = DecisionPayload(
        system_status="READY",
        requires_manual_review=False,
        decision_reason="RISK_THRESHOLD",
        data_validity="VALID",
        ml_execution_mode="FULL",
        risk_level="DANGER",
        probability=0.82,
        confidence_score=0.88,
        is_safe_for_automation=True,
    )
    pipeline_run = PipelineRunConfig(
        execution_mode="production",
        origin="Monas, Jakarta",
        destination="RSUP Fatmawati, Jakarta",
        api_version="v1",
        pipeline_version="agentic-v2.0",
    )

    result = execute_pipeline(
        snapshot_input=snapshot_input,
        location="Jakarta Selatan",
        perception=perception,
        reasoning=reasoning,
        evaluation=evaluation,
        decision=decision,
        pipeline_run=pipeline_run,
    )
    print(result_to_dict(result))


if __name__ == "__main__":
    main()

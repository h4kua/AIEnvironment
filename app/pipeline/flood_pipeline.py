"""
FloodDecisionPipeline — Orchestrator for the 5-stage agentic decision pipeline.

Stage flow:
  PerceptionAgent → ReasoningAgent → EvaluationAgent → ActionAgent → RoutingAgent

Each stage is independently testable and fails in isolation — the pipeline
degrades gracefully rather than crashing the API when one stage encounters
an unexpected error.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger(__name__)

from app.agents.action_agent import ActionAgent
from app.agents.evaluation_agent import EvaluationAgent
from app.agents.perception_agent import PerceptionAgent
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.routing_agent import RoutingAgent
from app.core.enums import (
    DATA_VALIDITY_INVALID,
    DECISION_REASON_FALLBACK,
    ML_EXECUTION_SHADOW_ONLY,
    RISK_LEVEL_UNKNOWN,
    SYSTEM_STATUS_PIPELINE_FAILURE,
)
from app.core.output_contract import (
    OutputContractError,
    safe_fallback_output,
    validate_output_schema,
)
from app.services.trend_analysis import compute_trend, record_prediction
from app.utils.paths import DEFAULT_REALTIME_SNAPSHOT

# Hydrology-dominant drivers that lose credibility when TMA data is unreliable.
_HYDRO_DRIVERS = {"critical_hydrology", "hydrology_stress"}


class FloodDecisionPipeline:
    """
    Orchestrates the 5-stage agentic flood decision pipeline.

    Usage:
        pipeline = FloodDecisionPipeline()
        result = pipeline.run(snapshot)                                    # no routing
        result = pipeline.run(snapshot, origin=..., destination=...)       # with routing
        result = pipeline.run_from_file()                                  # from default snapshot
        result = pipeline.run_from_file(path, origin=..., destination=...) # with routing
    """

    def __init__(self, *, strict_mode: bool = False) -> None:
        """
        Args:
            strict_mode: When False (default), an output-contract violation is
                logged and replaced with safe_fallback_output() so downstream
                consumers never see a malformed dict. When True, the
                OutputContractError is re-raised — useful for tests, debug
                runs, and CI pipelines where masking a bug is unacceptable.
                The agent-stage exception path (PIPELINE_FAILURE) is NOT
                affected by this flag — runtime crashes always degrade
                gracefully so the FastAPI surface never returns 500.
        """
        self._perception = PerceptionAgent()
        self._reasoning = ReasoningAgent()
        self._evaluation = EvaluationAgent()
        self._action = ActionAgent()
        self._routing = RoutingAgent()
        self._strict_mode = bool(strict_mode)

    def run(
        self,
        snapshot: dict,
        origin: str | None = None,
        destination: str | None = None,
    ) -> dict:
        """
        Execute the full pipeline on a snapshot dict.

        Returns the structured decision report. Guaranteed to return a valid
        dict even if a stage fails — pipeline failures return
        system_status='PIPELINE_FAILURE' with requires_manual_review=True.
        """
        t_start = time.perf_counter()

        try:
            perception = self._perception.run(snapshot)
        except Exception as exc:
            return self._emergency_output(f"PerceptionAgent failed: {exc}")

        try:
            reasoning = self._reasoning.run(perception)
        except Exception as exc:
            return self._emergency_output(f"ReasoningAgent failed: {exc}")

        try:
            evaluation = self._evaluation.run(reasoning, perception)
        except Exception as exc:
            return self._emergency_output(f"EvaluationAgent failed: {exc}")

        try:
            result = self._action.run(evaluation)
        except Exception as exc:
            return self._emergency_output(f"ActionAgent failed: {exc}")

        try:
            routing = self._routing.run(evaluation, origin, destination)
            result["safe_route"] = routing["safe_route"]
            result["tma_data"] = routing["tma_data"]
            if routing.get("tma_failure"):
                result["failure_modes"].append(routing["tma_failure"])
            if routing.get("confidence_adjustment", 0.0) < 0:
                result["confidence_score"] = round(
                    max(0.05, result["confidence_score"] + routing["confidence_adjustment"]),
                    4,
                )
        except Exception as exc:
            result["safe_route"] = {
                "available": False,
                "reason": f"RoutingAgent failed: {exc}",
                "flood_zones_checked": 0,
                "alternatives_evaluated": 0,
            }
            result["tma_data"] = None

        # ── Temporal trend (Task 2) ───────────────────────────────────────────
        try:
            record_prediction(
                probability=evaluation.probability,
                risk_level=evaluation.risk_level,
                water_level_ratio=evaluation.reasoning.signals.get("_water_level_ratio"),
                rainfall_mm=evaluation.reasoning.signals.get("_rainfall_mm"),
            )
            result["trend_analysis"] = compute_trend()
        except Exception:
            result["trend_analysis"] = {
                "risk_delta_1h": 0.0,
                "risk_trend": "unavailable",
                "water_level_trend": "unavailable",
                "rainfall_trend": "unavailable",
                "data_points": 0,
            }

        # ── TMA reliability — suppress hydrology-dominant driver (Task 5) ────
        tma_failed = any(
            f.get("type") == "external_source_unreliable"
            for f in result.get("failure_modes", [])
        )
        if tma_failed and result.get("dominant_risk_driver") in _HYDRO_DRIVERS:
            result["dominant_risk_driver"] = "hydrology_unverified"
            result["risk_interpretation"] = (
                result.get("risk_interpretation", "")
                + " [RELIABILITY NOTE: Hydrology assessment reduced — TMA water-level"
                " data unavailable. River-level signals cannot be independently verified.]"
            )
            result["system_interpretation"] = (
                "System operating with reduced hydrology reliability — TMA (Tinggi Muka Air) "
                "real-time data source is unavailable. Hydrology-driven risk signals are present "
                "but unverified by live sensor readings. "
                f"Risk: {result.get('risk_level', 'UNKNOWN')} "
                f"({result.get('confidence_score', 0.0):.0%} confidence)."
            )

        result["pipeline_execution_ms"] = round(
            (time.perf_counter() - t_start) * 1000, 1
        )
        result["pipeline_version"] = "agentic-v2.0"

        # ── Final output contract gate (MANDATORY) ──────────────────────────
        # Last-line defence: if any code path between PerceptionAgent and here
        # has produced a malformed or internally inconsistent output, replace
        # it with a safe-fallback dict so downstream consumers never see
        # silently corrupt data. The contract is verified once at this single
        # boundary point — no consumer needs to re-validate.
        #
        # Observability:
        #   1. The error is logged with full structured context — operators
        #      see every fallback even if the API consumer only sees the dict.
        #   2. The fallback dict carries a `contract_violation` block AND a
        #      `[L5-CONTRACT-FAILURE]` trace marker, so the failure cannot be
        #      silently masked downstream.
        #   3. In strict_mode the exception is re-raised — used by tests,
        #      debug runs, and CI to make a contract regression a hard fail.
        try:
            validate_output_schema(result)
        except OutputContractError as exc:
            error_type = type(exc).__name__
            _log.error(
                "OUTPUT_CONTRACT_VIOLATION error_type=%s message=%s "
                "system_status=%r risk_level=%r decision_reason=%r "
                "data_validity=%r ml_execution_mode=%r is_safe_for_automation=%r "
                "decision_source=%r",
                error_type,
                str(exc),
                result.get("system_status"),
                result.get("risk_level"),
                result.get("decision_reason"),
                result.get("data_validity"),
                result.get("ml_execution_mode"),
                result.get("is_safe_for_automation"),
                result.get("decision_source"),
            )
            if self._strict_mode:
                raise
            return safe_fallback_output(
                str(exc),
                error_type=error_type,
                original_result=result,
            )
        return result

    def run_from_file(
        self,
        snapshot_path: Path | str | None = None,
        origin: str | None = None,
        destination: str | None = None,
    ) -> dict:
        """Load snapshot JSON from disk and run the full pipeline."""
        path = Path(snapshot_path) if snapshot_path else DEFAULT_REALTIME_SNAPSHOT
        with open(path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        return self.run(snapshot, origin=origin, destination=destination)

    @staticmethod
    def _emergency_output(reason: str) -> dict:
        """
        Fallback when a stage raises an unhandled exception.

        Always returns a structurally valid response so the FastAPI endpoint
        never produces an opaque 500 — operators always receive actionable context.
        """
        return {
            "system_status": SYSTEM_STATUS_PIPELINE_FAILURE,
            "requires_manual_review": True,
            # Disambiguation layer — same contract as ActionAgent output.
            # Logically consistent: PIPELINE_FAILURE → FALLBACK → SHADOW_ONLY
            # → INVALID → not safe for automation.
            "decision_reason": DECISION_REASON_FALLBACK,
            "data_validity": DATA_VALIDITY_INVALID,
            "ml_execution_mode": ML_EXECUTION_SHADOW_ONLY,
            "is_safe_for_automation": False,
            "risk_level": RISK_LEVEL_UNKNOWN,
            "probability": 0.0,
            "confidence_score": 0.0,
            "dominant_risk_driver": "pipeline_error",
            "risk_interpretation": (
                f"Pipeline failure: {reason}. "
                "Automated assessment is unavailable — manual evaluation required."
            ),
            "recommended_action": [
                "IMMEDIATE: Automated prediction system is offline. "
                "Conduct manual flood assessment using field personnel and direct sensor readings."
            ],
            "failure_modes": [
                {
                    "type": "pipeline_error",
                    "severity": "critical",
                    "message": reason,
                    "detail": {},
                }
            ],
            "baseline_check": {
                "baseline_probability": 0.0,
                "rainfall_baseline": {},
                "hydro_baseline": {},
                "baseline_disagreement": 0.0,
                "baseline_alert": False,
                "model_vs_baseline": "unknown",
            },
            "data_freshness_minutes": -1.0,
            "signals": {},
            "diagnostics": {},
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": "agentic-v1.0",
            "model_name": "unknown",
        }

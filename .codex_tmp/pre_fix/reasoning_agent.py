"""
ReasoningAgent — Stage 2 of the agentic flood decision pipeline.

Responsibility:
  - Run the realtime-native ML model on the current snapshot
  - Independently compute a rule-based baseline probability
  - Detect data/signal failures
  - Extract multi-condition risk signals
  - Generate an expert-style risk interpretation

Separates "what the model says" from "what the signals say" so the
EvaluationAgent can reconcile them with explicit trust accounting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import joblib
import numpy as np

from app.realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_snapshot,
)
from app.services.adaptive_threshold import AdaptiveThresholder
from app.services.baseline_check import compare_with_baseline
from app.services.decision_logic import (
    build_context_summary,
    dominant_risk_driver,
    extract_signals,
    generate_risk_interpretation,
)
from app.services.failure_handling import detect_failures
from app.utils.paths import MODELS_DIR

if TYPE_CHECKING:
    from app.agents.perception_agent import PerceptionResult


# ─── Model asset loading ──────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_assets() -> tuple:
    """Load and cache realtime-native model assets on first call."""
    model = joblib.load(MODELS_DIR / "flood_model_realtime_native.pkl")
    scaler = joblib.load(MODELS_DIR / "scaler_realtime_native.pkl")
    ood_detector = joblib.load(MODELS_DIR / "ood_detector_realtime_native.pkl")
    with open(MODELS_DIR / "model_card_realtime_native.json", encoding="utf-8") as fh:
        model_card = json.load(fh)
    return model, scaler, ood_detector, model_card


def _to_native(value: Any) -> Any:
    """Recursively convert numpy scalars to Python built-ins for JSON safety."""
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _base_confidence(probability: float, ood_score: float) -> float:
    """
    Compute initial model confidence before failure penalties are applied.

    Two components:
      - Margin score: normalised distance from the nearest classification threshold.
        Thresholds are 0.20 and 0.45; we normalise against 0.25 so clear
        predictions (far from both thresholds) score near 1.0.
      - OOD confidence: IsolationForest decision_function mapped to [0, 1].
        Typical range [-0.5, 0.2]; we map this so score > 0 → near 1.0,
        score < -0.5 → 0.0.
    """
    min_dist = min(abs(probability - 0.20), abs(probability - 0.45))
    margin_score = min(min_dist / 0.25, 1.0)
    ood_confidence = max(0.0, min(1.0, (ood_score + 0.50) / 0.70))
    return round(margin_score * 0.60 + ood_confidence * 0.40, 4)


def _run_model(snapshot: dict) -> dict:
    """
    Execute the realtime-native model pipeline on a snapshot dict.

    Uses persist_history=True so the temporal feature history CSV is updated
    exactly once per pipeline invocation (flood_pipeline.py does not call this twice).
    """
    model, scaler, ood_detector, model_card = _load_assets()

    engineered = build_realtime_native_features_from_snapshot(snapshot, persist_history=True)
    features_df = engineered.frame[REALTIME_NATIVE_FEATURES]
    scaled = scaler.transform(features_df)

    probability = float(model.predict_proba(scaled)[0, 1])
    ood_score = float(ood_detector.decision_function(scaled)[0])
    ood_is_outlier = bool(ood_detector.predict(scaled)[0] == -1)

    return {
        "model_variant": "realtime_native",
        "probability": round(probability, 4),
        "confidence_score": _base_confidence(probability, ood_score),
        "ood_detection": {
            "method": "IsolationForest",
            "score": round(ood_score, 4),
            "is_outlier": ood_is_outlier,
        },
        "features": _to_native(features_df.iloc[0].to_dict()),
        "diagnostics": _to_native(engineered.diagnostics),
        "model_name": model_card.get("model_name", "XGBoost Flood Predictor - Realtime Native"),
    }


# ─── ReasoningResult ──────────────────────────────────────────────────────────


@dataclass
class ReasoningResult:
    """Structured output of ReasoningAgent. Passed directly to EvaluationAgent."""

    features: dict
    diagnostics: dict
    prediction: dict
    signals: dict
    dominant_driver: str
    context_summary: dict
    risk_interpretation: str
    failure_modes: list
    baseline_result: dict


# ─── ReasoningAgent ───────────────────────────────────────────────────────────


class ReasoningAgent:
    """
    Stage 2: Reasoning.

    Orchestrates four independent sub-computations:
      1. ML model inference (realtime-native XGBoost + IsolationForest OOD)
      2. Rule-based baseline estimation (rainfall + hydro physical rules)
      3. Failure detection (missing data, signal conflicts, OOD)
      4. Multi-condition signal extraction and expert narrative generation
    """

    def run(self, perception: "PerceptionResult") -> ReasoningResult:
        # Step 1: ML model — features + OOD detection + probability
        prediction = _run_model(perception.snapshot)
        features = prediction["features"]
        diagnostics = prediction["diagnostics"]
        model_prob = prediction["probability"]
        ood_detection = prediction["ood_detection"]

        # Step 2: Rule-based baseline (independent of model output)
        baseline_result = compare_with_baseline(model_prob, features)

        # Step 3: Failure detection across all failure categories
        failure_modes = detect_failures(
            snapshot=perception.snapshot,
            features=features,
            diagnostics=diagnostics,
            model_prob=model_prob,
            baseline_result=baseline_result,
            ood_detection=ood_detection,
        )

        # Step 4: Adaptive threshold classification (replaces static _classify)
        trend_state: dict = diagnostics.get("trend_state") or {}
        # Direct attribute access — no optimistic 1.0 default.
        # If PerceptionAgent never set plausibility_score, this raises AttributeError,
        # which the pipeline catches as PIPELINE_FAILURE rather than silently treating
        # unvalidated data as fully trustworthy.
        plausibility_score: float = perception.plausibility_score
        adaptive_cls = AdaptiveThresholder().classify(
            probability=model_prob,
            failure_modes=failure_modes,
            trend_state=trend_state,
            plausibility_score=plausibility_score,
        )
        prediction["risk_level"] = adaptive_cls.risk_level
        prediction["adaptive_classification"] = adaptive_cls.to_dict()

        # Step 5: Signal extraction with plausibility gate.
        # Sensor-derived signals (rainfall, water level) are suppressed when
        # plausibility is low so RoutingAgent never builds flood zones from OOD data.
        signals = extract_signals(features, plausibility_score=plausibility_score)
        driver = dominant_risk_driver(features, plausibility_score=plausibility_score)
        signals["dominant_driver"] = driver

        context_summary = build_context_summary(features, diagnostics, prediction, baseline_result, plausibility_score=plausibility_score)
        risk_interpretation = generate_risk_interpretation(signals, failure_modes)

        return ReasoningResult(
            features=features,
            diagnostics=diagnostics,
            prediction=prediction,
            signals=signals,
            dominant_driver=driver,
            context_summary=context_summary,
            risk_interpretation=risk_interpretation,
            failure_modes=failure_modes,
            baseline_result=baseline_result,
        )

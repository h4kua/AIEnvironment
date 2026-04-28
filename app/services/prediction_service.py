import json
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np

from app.services.model_registry import load_model_assets
from app.services.report_service import refresh_project_summary
from app.services.realtime_adapter import adapt_snapshot_to_features, load_realtime_snapshot
from app.services.training_data_monitor import detect_out_of_distribution
from app.utils.paths import DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR


OVERFITTING_GAP_WARNING = 0.05


def _resolve_probability(model, scaled_features):
    probability = model.predict_proba(scaled_features)[0, 1]
    return float(probability)


def _classify_risk(probability, threshold):
    if probability < threshold * 0.5:
        return "SAFE"
    if probability < threshold:
        return "WARNING"
    return "DANGER"


def _get_base_model(model):
    for attr in ("base_estimator", "estimator", "model"):
        candidate = getattr(model, attr, None)
        if candidate is not None:
            return candidate
    return model


@lru_cache(maxsize=1)
def _get_shap_explainer():
    try:
        import shap
    except ImportError:
        return None

    assets = load_model_assets()
    return shap.TreeExplainer(_get_base_model(assets.model))


@lru_cache(maxsize=128)
def _cached_explanation(feature_signature):
    explainer = _get_shap_explainer()
    if explainer is None:
        return None

    assets = load_model_assets()
    feature_array = np.array(feature_signature, dtype=float).reshape(1, -1)
    shap_values = explainer.shap_values(feature_array)
    if isinstance(shap_values, list):
        shap_values = shap_values[-1]

    contributions = []
    for feature_name, shap_value, feature_value in zip(
        assets.feature_names,
        shap_values[0],
        feature_array[0],
    ):
        contributions.append(
            {
                "feature": feature_name,
                "feature_value": float(feature_value),
                "shap_value": float(shap_value),
                "impact": "increase_risk" if shap_value >= 0 else "decrease_risk",
            }
        )

    contributions.sort(key=lambda item: abs(item["shap_value"]), reverse=True)
    return contributions[:3]


def _build_explanation(ordered_features):
    rounded_signature = tuple(round(float(value), 4) for value in ordered_features.iloc[0].tolist())
    try:
        return _cached_explanation(rounded_signature)
    except Exception:
        return None


def _write_latest_prediction_report(prediction):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "latest_realtime_prediction.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(prediction, file, ensure_ascii=False, indent=2)


def _to_builtin(value):
    if isinstance(value, dict):
        return {key: _to_builtin(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_builtin(item) for item in value]
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def _compute_model_warning(assets, ood_result, data_quality_score):
    warnings = []
    model_gap = float(
        assets.project_summary.get("performance", {}).get("train_test_accuracy_gap", 0.0559)
    )
    if model_gap >= OVERFITTING_GAP_WARNING:
        warnings.append(
            {
                "type": "overfitting_risk",
                "severity": "medium",
                "message": "Train-test gap masih menunjukkan risiko overfitting moderat untuk kondisi realtime ekstrem.",
                "value": model_gap,
            }
        )

    if ood_result["out_of_distribution_count"] >= 3:
        warnings.append(
            {
                "type": "out_of_distribution",
                "severity": "high",
                "message": "Beberapa feature berada di luar distribusi training Jakarta.",
                "details": ood_result["warnings"],
            }
        )

    if data_quality_score < 0.7:
        warnings.append(
            {
                "type": "data_quality",
                "severity": "medium",
                "message": "Kualitas data realtime sedang/rendah; lebih banyak feature berbasis estimasi daripada observasi langsung.",
                "value": data_quality_score,
            }
        )

    return warnings


def _compute_confidence_score(probability, threshold, data_quality_score, ood_ratio):
    margin = abs(probability - threshold)
    normalized_margin = min(margin / max(threshold, 1 - threshold, 0.01), 1.0)
    confidence_score = (
        normalized_margin * 0.35
        + data_quality_score * 0.4
        + max(0.0, min(ood_ratio, 1.0)) * 0.25
    )
    return round(min(max(confidence_score, 0.0), 1.0), 4)


def predict_realtime(snapshot_path=None, include_explanation=True):
    assets = load_model_assets()
    snapshot = load_realtime_snapshot(snapshot_path or DEFAULT_REALTIME_SNAPSHOT)
    adapted = adapt_snapshot_to_features(snapshot)
    ordered_features = adapted.feature_frame[assets.feature_names]
    scaled_features = assets.scaler.transform(ordered_features)
    probability = _resolve_probability(assets.model, scaled_features)
    threshold = float(assets.threshold_config["optimal_threshold_f1"])
    risk_level = _classify_risk(probability, threshold)
    ood_result = detect_out_of_distribution(ordered_features.iloc[0].to_dict())
    confidence_score = _compute_confidence_score(
        probability=probability,
        threshold=threshold,
        data_quality_score=adapted.data_quality["score"],
        ood_ratio=ood_result["in_distribution_ratio"],
    )
    model_warning = _compute_model_warning(
        assets=assets,
        ood_result=ood_result,
        data_quality_score=adapted.data_quality["score"],
    )

    prediction = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "probability": probability,
        "risk_level": risk_level,
        "threshold": threshold,
        "confidence_score": confidence_score,
        "data_quality": _to_builtin(adapted.data_quality),
        "model_warning": _to_builtin(model_warning),
        "distribution_check": _to_builtin(ood_result),
        "model_name": assets.model_card.get("model_name"),
        "features": _to_builtin(ordered_features.iloc[0].to_dict()),
        "diagnostics": _to_builtin(adapted.diagnostics),
        "source_snapshot": str(snapshot_path or DEFAULT_REALTIME_SNAPSHOT),
        "pipeline_version": "legacy-v1.0",
    }

    if include_explanation:
        prediction["explanation"] = _build_explanation(ordered_features)

    _write_latest_prediction_report(prediction)
    refresh_project_summary(prediction)
    return prediction

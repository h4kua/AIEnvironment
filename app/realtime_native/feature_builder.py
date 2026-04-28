import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.services.constants import (
    BMKG_CERTAINTY_WEIGHTS,
    BMKG_SEVERITY_WEIGHTS,
    BMKG_URGENCY_WEIGHTS,
)
from app.services.trend_analysis import compute_trend
from app.utils.paths import DEFAULT_REALTIME_SNAPSHOT, PROCESSED_DATA_DIR


REALTIME_NATIVE_HISTORY_PATH = PROCESSED_DATA_DIR / "realtime_feature_history.csv"
REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH = PROCESSED_DATA_DIR / "realtime_native_training_bootstrap.csv"

REALTIME_NATIVE_FEATURES = [
    "rainfall_mm",
    "rainfall_3h_proxy_mm",
    "rainfall_lag_1",
    "rainfall_lag_2",
    "rainfall_roll3_mean",
    "humidity_pct",
    "temperature_c",
    "bmkg_severity_score",
    "bmkg_certainty_score",
    "bmkg_urgency_score",
    "bmkg_weighted_score",
    "water_level_ratio",
    "water_level_lag_1",
    "water_level_delta",
    "hydro_meteorological_index",
    "monsoon_season",
]


@dataclass(frozen=True)
class RealtimeNativeFeatures:
    frame: pd.DataFrame
    diagnostics: dict


def _safe_float(value, default=0.0):
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value):
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _bmkg_category_scores_from_alerts(alerts):
    severity_map = BMKG_SEVERITY_WEIGHTS
    certainty_map = BMKG_CERTAINTY_WEIGHTS
    urgency_map = BMKG_URGENCY_WEIGHTS

    if not alerts:
        return {
            "bmkg_severity_score": 0.0,
            "bmkg_certainty_score": 0.0,
            "bmkg_urgency_score": 0.0,
            "bmkg_weighted_score": 0.0,
        }

    severity_scores = []
    certainty_scores = []
    urgency_scores = []
    weighted_scores = []
    for alert in alerts:
        severity = severity_map.get((alert.get("severity") or "").lower(), 0.4)
        certainty = certainty_map.get((alert.get("certainty") or "").lower(), 0.4)
        urgency = urgency_map.get((alert.get("urgency") or "").lower(), 0.5)
        severity_scores.append(severity)
        certainty_scores.append(certainty)
        urgency_scores.append(urgency)
        weighted_scores.append(severity * certainty * urgency)

    return {
        "bmkg_severity_score": max(severity_scores),
        "bmkg_certainty_score": max(certainty_scores),
        "bmkg_urgency_score": max(urgency_scores),
        "bmkg_weighted_score": min(sum(weighted_scores), 1.0),
    }


def _bmkg_category_scores_from_rainfall(rainfall_mm, rainfall_recent_mm):
    severity = 0.25
    if rainfall_mm >= 80:
        severity = 1.0
    elif rainfall_mm >= 50:
        severity = 0.8
    elif rainfall_mm >= 25:
        severity = 0.5

    certainty = min(max(rainfall_recent_mm / max(rainfall_mm, 1.0), 0.2), 1.0)
    urgency = 1.0 if rainfall_mm >= 50 else 0.75 if rainfall_mm >= 25 else 0.4
    weighted = severity * certainty * urgency
    return {
        "bmkg_severity_score": round(severity, 4),
        "bmkg_certainty_score": round(certainty, 4),
        "bmkg_urgency_score": round(urgency, 4),
        "bmkg_weighted_score": round(weighted, 4),
    }


def _water_level_ratio_from_records(records):
    best_ratio = 0.0
    for record in (records or []):
        current_level = _safe_float(record.get("tinggi_air"))
        thresholds = [
            _safe_float(record.get("siaga1")),
            _safe_float(record.get("siaga2")),
            _safe_float(record.get("siaga3")),
            _safe_float(record.get("siaga4")),
        ]
        thresholds = [threshold for threshold in thresholds if threshold > 0]
        if not thresholds:
            continue
        ratio = current_level / max(thresholds)
        best_ratio = max(best_ratio, ratio)
    return min(best_ratio, 1.5)


def _load_history(path=REALTIME_NATIVE_HISTORY_PATH):
    if not Path(path).exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _append_history(row, path=REALTIME_NATIVE_HISTORY_PATH):
    history = _load_history(path)
    updated = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    updated.tail(2000).to_csv(path, index=False)


def _add_temporal_columns(current_row, history):
    if history.empty:
        history = pd.DataFrame(columns=["rainfall_mm", "water_level_ratio"])

    rainfall_history = history["rainfall_mm"].tolist() if "rainfall_mm" in history.columns else []
    water_history = history["water_level_ratio"].tolist() if "water_level_ratio" in history.columns else []

    rainfall_lag_1 = rainfall_history[-1] if len(rainfall_history) >= 1 else current_row["rainfall_3h_proxy_mm"]
    rainfall_lag_2 = rainfall_history[-2] if len(rainfall_history) >= 2 else rainfall_lag_1
    rolling_values = (rainfall_history[-2:] if len(rainfall_history) >= 2 else rainfall_history) + [current_row["rainfall_mm"]]
    rainfall_roll3_mean = sum(rolling_values) / max(len(rolling_values), 1)

    water_level_lag_1 = water_history[-1] if len(water_history) >= 1 else current_row["water_level_ratio"]
    water_level_delta = current_row["water_level_ratio"] - water_level_lag_1

    current_row.update(
        {
            "rainfall_lag_1": rainfall_lag_1,
            "rainfall_lag_2": rainfall_lag_2,
            "rainfall_roll3_mean": rainfall_roll3_mean,
            "water_level_lag_1": water_level_lag_1,
            "water_level_delta": water_level_delta,
        }
    )
    return current_row


def build_realtime_native_features_from_snapshot(snapshot, persist_history=True):
    timestamp = _parse_timestamp(snapshot.get("fetched_at_utc"))
    weather = snapshot.get("openweather", {})
    main_weather = weather.get("main", {})
    rain_data = weather.get("rain", {})
    poskobanjir_records = snapshot.get("poskobanjir") or []
    alerts = snapshot.get("bmkg_alerts") or []

    rainfall_mm = max(
        _safe_float(rain_data.get("1h")),
        _safe_float(rain_data.get("3h")) / 3 if rain_data.get("3h") is not None else 0.0,
    )
    rainfall_3h_proxy_mm = max(_safe_float(rain_data.get("3h")), rainfall_mm * 3)
    humidity_pct = _safe_float(main_weather.get("humidity"), 75.0)
    temperature_c = _safe_float(main_weather.get("temp"), 30.0)
    water_level_ratio = _water_level_ratio_from_records(poskobanjir_records)
    bmkg_scores = _bmkg_category_scores_from_alerts(alerts)

    current_row = {
        "timestamp": timestamp.isoformat(),
        "rainfall_mm": rainfall_mm,
        "rainfall_3h_proxy_mm": rainfall_3h_proxy_mm,
        "humidity_pct": humidity_pct,
        "temperature_c": temperature_c,
        "water_level_ratio": water_level_ratio,
        "monsoon_season": int(timestamp.month in [11, 12, 1, 2, 3]),
        **bmkg_scores,
    }

    history = _load_history()
    current_row = _add_temporal_columns(current_row, history)
    current_row["hydro_meteorological_index"] = (
        current_row["rainfall_roll3_mean"] * (humidity_pct / 100.0) * (1 + water_level_ratio)
    )

    # Momentum features computed from past data only (no leakage).
    # rainfall_lag_1 is 0-history fallback set by _add_temporal_columns.
    _rf_lag1 = current_row.get("rainfall_lag_1", current_row["rainfall_mm"])
    _rf_lag2 = current_row.get("rainfall_lag_2", _rf_lag1)
    diagnostics = {
        "history_rows_used": int(len(history)),
        "temporal_features_ready": len(history) >= 2,
        "bmkg_source": "observed_alerts" if alerts else "no_alert",
        "water_level_records": len(poskobanjir_records),
        # Momentum scalars (top-level for direct diagnostics consumers).
        "rainfall_trend_mm_h": round(current_row["rainfall_mm"] - _rf_lag1, 4),
        "rainfall_acc_3h": round(current_row.get("rainfall_3h_proxy_mm", 0.0), 4),
        "rainfall_acc_6h": round(current_row["rainfall_mm"] + _rf_lag1 + _rf_lag2, 4),
        "water_level_trend": round(current_row.get("water_level_delta", 0.0), 4),
        # Trend state: ring-buffer trend + embedded momentum so AdaptiveThresholder
        # can access physical context through its existing trend_state parameter.
        "trend_state": {
            **compute_trend(),
            "rainfall_acc_3h": round(current_row.get("rainfall_3h_proxy_mm", 0.0), 4),
            "rainfall_trend_mm_h": round(current_row["rainfall_mm"] - _rf_lag1, 4),
            "water_level_delta_cur": round(current_row.get("water_level_delta", 0.0), 4),
        },
    }

    if persist_history:
        _append_history(
            {
                "timestamp": current_row["timestamp"],
                "rainfall_mm": current_row["rainfall_mm"],
                "water_level_ratio": current_row["water_level_ratio"],
            }
        )

    feature_row = {name: current_row[name] for name in REALTIME_NATIVE_FEATURES}
    return RealtimeNativeFeatures(frame=pd.DataFrame([feature_row]), diagnostics=diagnostics)


def build_realtime_native_features_from_file(snapshot_path=DEFAULT_REALTIME_SNAPSHOT, persist_history=True):
    with open(snapshot_path, "r", encoding="utf-8") as file:
        snapshot = json.load(file)
    return build_realtime_native_features_from_snapshot(snapshot, persist_history=persist_history)


def build_bootstrap_training_dataset(
    input_path=PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv",
    output_path=REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
):
    df = pd.read_csv(input_path).copy()
    df["timestamp"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).astype(str) + "-01",
        errors="coerce",
    )
    df = df.sort_values(["jakarta_region", "name_3", "timestamp"]).reset_index(drop=True)

    # Bootstrap features: transparan bahwa beberapa field adalah proxy sampai histori realtime observasional tersedia.
    df["rainfall_mm"] = pd.to_numeric(df["max_rainfall"], errors="coerce")
    df["rainfall_3h_proxy_mm"] = df["rainfall_mm"] * 1.8
    df["humidity_pct"] = (
        pd.to_numeric(df["soil_moisture"], errors="coerce") * 1.75
        + pd.to_numeric(df["avg_rainfall"], errors="coerce") * 0.18
    ).clip(45, 100)
    df["temperature_c"] = pd.to_numeric(
        df["avg_temperature"] if "avg_temperature" in df.columns else pd.Series(dtype=float),
        errors="coerce",
    ).fillna(28.5)

    rainfall_recent = pd.to_numeric(df["avg_rainfall"], errors="coerce")
    bmkg_proxy = df.apply(
        lambda row: _bmkg_category_scores_from_rainfall(
            rainfall_mm=_safe_float(row["rainfall_mm"]),
            rainfall_recent_mm=_safe_float(row["avg_rainfall"]),
        ),
        axis=1,
    )
    bmkg_proxy_df = pd.DataFrame(list(bmkg_proxy))
    df = pd.concat([df, bmkg_proxy_df], axis=1)

    water_level_ratio = (
        pd.to_numeric(df["max_rainfall"], errors="coerce") / pd.to_numeric(df["max_rainfall"], errors="coerce").quantile(0.95)
    ).clip(0, 1.5)
    df["water_level_ratio"] = water_level_ratio

    group_keys = ["jakarta_region", "name_3"]
    df["rainfall_lag_1"] = df.groupby(group_keys)["rainfall_mm"].shift(1)
    df["rainfall_lag_2"] = df.groupby(group_keys)["rainfall_mm"].shift(2)
    df["rainfall_roll3_mean"] = (
        df.groupby(group_keys)["rainfall_mm"]
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=group_keys, drop=True)
    )
    df["water_level_lag_1"] = df.groupby(group_keys)["water_level_ratio"].shift(1)
    df["water_level_delta"] = df["water_level_ratio"] - df["water_level_lag_1"]
    df["hydro_meteorological_index"] = (
        df["rainfall_roll3_mean"] * (df["humidity_pct"] / 100.0) * (1 + df["water_level_ratio"])
    )
    df["monsoon_season"] = df["month"].astype(int).isin([11, 12, 1, 2, 3]).astype(int)

    df["rainfall_lag_1"] = df["rainfall_lag_1"].fillna(df["rainfall_mm"])
    df["rainfall_lag_2"] = df["rainfall_lag_2"].fillna(df["rainfall_lag_1"])
    df["water_level_lag_1"] = df["water_level_lag_1"].fillna(df["water_level_ratio"])
    df["water_level_delta"] = df["water_level_delta"].fillna(0.0)

    df["feature_provenance"] = "bootstrap_proxy"

    selected_columns = [
        "timestamp",
        "jakarta_region",
        "name_3",
        *REALTIME_NATIVE_FEATURES,
        "banjir",
        "feature_provenance",
    ]
    output_df = df[selected_columns]
    output_df.to_csv(output_path, index=False)
    return output_df

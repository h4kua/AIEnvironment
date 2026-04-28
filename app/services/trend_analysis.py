"""
Temporal trend analysis — tracks risk evolution across recent pipeline predictions.

Upgrades over baseline implementation:
  - History buffer: 8 predictions (was 3) for better trend resolution
  - Weighted trend: exponential weights so recent readings dominate
  - Rate-of-change: computed against actual timestamps (probability per hour)
  - Trend confidence: directional consistency across all consecutive pairs
  - Spike detection: single-step probability jump >= SPIKE_THRESHOLD
  - Slow accumulation: monotone rising trend sustained over ACCUMULATION_STEPS
  - Richer output: trend_strength, trend_confidence, anomaly_detected, anomaly_type

Public API (unchanged signatures — backward compatible):
  record_prediction(probability, risk_level, water_level_ratio, rainfall_mm) -> None
  compute_trend() -> dict  (richer output; all prior keys preserved)
  reset_history() -> None

The module-level ring buffer persists across API requests (process lifetime),
giving the system memory of recent conditions — essential for detecting rapid-onset
events that appear mild on a single reading.
"""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timezone
from threading import Lock

_HISTORY_SIZE = 8
_history: deque = deque(maxlen=_HISTORY_SIZE)
_lock = Lock()

# Trend classification thresholds
_PROB_TREND_THRESHOLD     = 0.08    # Weighted delta to classify increasing/decreasing
_WL_TREND_THRESHOLD       = 0.04    # Water-level ratio delta
_RAINFALL_TREND_THRESHOLD = 4.0     # Rainfall mm delta

# Anomaly detection thresholds
_SPIKE_THRESHOLD       = 0.20   # Single-step probability jump = spike event
_ACCUMULATION_STEPS    = 4      # Consecutive rising steps to flag slow accumulation
_MIN_RATE_HOURS        = 0.005  # ~18 seconds — guard against divide-by-zero


def record_prediction(
    probability: float,
    risk_level: str,
    water_level_ratio: float | None,
    rainfall_mm: float | None,
) -> None:
    """Append a completed prediction snapshot to the ring buffer."""
    with _lock:
        _history.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "probability": probability,
            "risk_level": risk_level,
            "water_level_ratio": water_level_ratio,
            "rainfall_mm": rainfall_mm,
        })


def compute_trend() -> dict:
    """
    Derive rich trend signals from the prediction ring buffer.

    Returns:
    {
        "risk_delta_1h":       float  — exponentially-weighted probability change
        "risk_rate_per_hour":  float  — probability change per actual elapsed hour
        "risk_trend":          str    — "increasing"|"decreasing"|"stable"|"insufficient_data"
        "trend_strength":      float  — 0.0-1.0 (normalised to 0.40 delta = max strength)
        "trend_confidence":    float  — 0.0-1.0 directional consistency across steps
        "water_level_trend":   str    — "rising"|"falling"|"stable"|"insufficient_data"
        "rainfall_trend":      str    — "intensifying"|"easing"|"stable"|"insufficient_data"
        "anomaly_detected":    bool
        "anomaly_type":        str|None — "spike"|"slow_accumulation"|None
        "data_points":         int
    }

    All keys from the previous implementation are preserved for backward
    compatibility with flood_pipeline.py and downstream consumers.
    """
    with _lock:
        history = list(_history)

    n = len(history)
    if n < 2:
        return _insufficient(n)

    probs = [h["probability"] for h in history]

    # ── Exponentially-weighted probability trend ─────────────────────────────
    # Weight for point i: exp(0.5 * (i - (n-1))); newest point has weight 1.0.
    weights = [math.exp(0.5 * (i - (n - 1))) for i in range(n)]
    w_sum = sum(weights)

    w_mean_t = sum(w * i for i, w in enumerate(weights)) / w_sum
    w_mean_p = sum(w * p for w, p in zip(weights, probs)) / w_sum

    numerator = sum(
        w * (i - w_mean_t) * (p - w_mean_p)
        for i, (w, p) in enumerate(zip(weights, probs))
    )
    denominator = sum(w * (i - w_mean_t) ** 2 for i, w in enumerate(weights))
    slope = numerator / denominator if abs(denominator) > 1e-9 else 0.0

    weighted_delta = round(slope * (n - 1), 4)

    # ── Rate of change vs real elapsed time ──────────────────────────────────
    rate_per_hour = _compute_hourly_rate(history)

    # ── Risk trend label ──────────────────────────────────────────────────────
    if weighted_delta > _PROB_TREND_THRESHOLD:
        risk_trend = "increasing"
    elif weighted_delta < -_PROB_TREND_THRESHOLD:
        risk_trend = "decreasing"
    else:
        risk_trend = "stable"

    # ── Trend strength (0.0-1.0) ──────────────────────────────────────────────
    trend_strength = round(min(abs(weighted_delta) / 0.40, 1.0), 4)

    # ── Trend confidence: fraction of consecutive pairs in majority direction ──
    trend_confidence = _directional_consistency(probs)

    # ── Auxiliary signal trends ───────────────────────────────────────────────
    wl_trend = _scalar_trend(
        [h["water_level_ratio"] for h in history],
        _WL_TREND_THRESHOLD,
        ("rising", "falling", "stable"),
    )
    rf_trend = _scalar_trend(
        [h["rainfall_mm"] for h in history],
        _RAINFALL_TREND_THRESHOLD,
        ("intensifying", "easing", "stable"),
    )

    # ── Anomaly detection ─────────────────────────────────────────────────────
    anomaly_type = _detect_anomaly(probs)

    return {
        # Legacy keys preserved for backward compatibility
        "risk_delta_1h": weighted_delta,
        "risk_trend": risk_trend,
        "water_level_trend": wl_trend,
        "rainfall_trend": rf_trend,
        "data_points": n,
        # New enriched keys
        "risk_rate_per_hour": rate_per_hour,
        "trend_strength": trend_strength,
        "trend_confidence": trend_confidence,
        "anomaly_detected": anomaly_type is not None,
        "anomaly_type": anomaly_type,
    }


def reset_history() -> None:
    """Clear the ring buffer. Used in scenario testing to isolate runs."""
    with _lock:
        _history.clear()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _insufficient(n: int) -> dict:
    return {
        "risk_delta_1h": 0.0,
        "risk_trend": "insufficient_data",
        "water_level_trend": "insufficient_data",
        "rainfall_trend": "insufficient_data",
        "data_points": n,
        "risk_rate_per_hour": 0.0,
        "trend_strength": 0.0,
        "trend_confidence": 0.0,
        "anomaly_detected": False,
        "anomaly_type": None,
    }


def _compute_hourly_rate(history: list[dict]) -> float:
    """Probability change rate per actual elapsed hour using stored timestamps."""
    try:
        t_old = datetime.fromisoformat(history[0]["timestamp_utc"])
        t_new = datetime.fromisoformat(history[-1]["timestamp_utc"])
        elapsed_hours = max((t_new - t_old).total_seconds() / 3600.0, _MIN_RATE_HOURS)
        delta = history[-1]["probability"] - history[0]["probability"]
        return round(delta / elapsed_hours, 4)
    except (KeyError, ValueError, TypeError):
        return 0.0


def _scalar_trend(
    values: list,
    threshold: float,
    labels: tuple[str, str, str],
) -> str:
    """
    Classify oldest→newest delta as labels[0]/labels[1]/labels[2] (up/down/stable).
    Returns "insufficient_data" if fewer than 2 non-None values exist.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "insufficient_data"
    delta = clean[-1] - clean[0]
    if delta > threshold:
        return labels[0]
    if delta < -threshold:
        return labels[1]
    return labels[2]


def _directional_consistency(probs: list[float]) -> float:
    """
    Fraction of consecutive pairs going in the majority direction.

    1.0 = all pairs move the same way (perfect trend).
    0.5 = half up half down (no clear trend).
    0.0 = perfectly alternating (anti-trend / noise).
    """
    if len(probs) < 2:
        return 0.0
    deltas = [probs[i + 1] - probs[i] for i in range(len(probs) - 1)]
    positive = sum(1 for d in deltas if d > 0)
    negative = sum(1 for d in deltas if d < 0)
    majority = max(positive, negative)
    return round(majority / len(deltas), 4)


def _detect_anomaly(probs: list[float]) -> str | None:
    """
    Detect two anomaly patterns:

    spike:             Any single consecutive-pair delta >= SPIKE_THRESHOLD.
                       Represents rapid-onset events (e.g. dam release, flash flood).

    slow_accumulation: All ACCUMULATION_STEPS most-recent values form a strict
                       monotone increasing sequence (no large single jump, but
                       sustained risk creep that may precede a threshold crossing).

    Spike takes priority if both conditions hold.
    Returns the anomaly type string, or None if no anomaly.
    """
    if len(probs) < 2:
        return None

    for i in range(len(probs) - 1):
        if abs(probs[i + 1] - probs[i]) >= _SPIKE_THRESHOLD:
            return "spike"

    if len(probs) >= _ACCUMULATION_STEPS:
        tail = probs[-_ACCUMULATION_STEPS:]
        if all(tail[i + 1] > tail[i] for i in range(len(tail) - 1)):
            return "slow_accumulation"

    return None

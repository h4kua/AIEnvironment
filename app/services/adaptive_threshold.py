"""
AdaptiveThresholder — context-aware risk classification for flood prediction.

Problem context:
  The realtime-native model is trained on monthly historical averages (bootstrap
  data), so its raw probability rarely exceeds 0.45 even for extreme events that
  are physically unambiguous. A fixed 0.45 DANGER threshold produces 100% FNR
  for DANGER under that training regime.

Solution strategy — two-layer approach:
  Layer 1 (this module): Threshold adjustment based on context signals.
    Lowers DANGER threshold when trend anomalies, physical plausibility, and
    signal patterns confirm escalation independently of the model.
  Layer 2 (failure_handling.has_danger_escalation): Physical safety override.
    Forces DANGER when multiple independent hazard channels are simultaneously
    extreme AND the input is physically plausible.

Threshold adjustment logic:
  OOD input          → +0.10 (raise: sensor faults must NOT trigger DANGER)
  Missing data       → +0.05 (raise: conservatism under incomplete observation)
  Trend anomaly      → -0.06 (lower: historical escalation pattern confirmed)
  Rapid rise         → -0.05 (lower: imminent danger window, stacked with anomaly)
  High plausibility  → -0.04 (lower: physically realistic extreme, trust signals)
  Signal conflict    → -0.07 (lower: baseline may see danger model undersells)
  Hard floor / ceil  → [0.25, 0.55]

All adjustments recorded in AdaptiveClassification for complete auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ─── Base classification boundaries ──────────────────────────────────────────

BASE_SAFE_THRESHOLD: float = 0.20    # prob < 0.20  → SAFE
BASE_DANGER_THRESHOLD: float = 0.45  # prob >= 0.45 → DANGER; 0.20–0.45 → WARNING

# ─── Adjustment magnitude constants ──────────────────────────────────────────

_ADJ_OOD_RAISE       = +0.10   # sensor malfunction — extreme values are noise
_ADJ_MISSING_RAISE   = +0.05   # missing data — cannot verify claims of extremity
_ADJ_TREND_ANOMALY   = -0.06   # anomaly in 8-step trend history → escalation pattern
_ADJ_RAPID_RISE      = -0.05   # rate > 0.04/hr → imminent danger development window
_ADJ_HIGH_PLAUS      = -0.04   # plausibility >= 0.90 → physically realistic extreme
_ADJ_CONFLICT_LOWER  = -0.07   # signal_conflict → baseline may see danger ML misses

_MIN_DANGER_THRESHOLD: float = 0.25   # hard floor — never ultra-sensitive
_MAX_DANGER_THRESHOLD: float = 0.55   # hard ceiling — never ultra-conservative

_PLAUSIBILITY_HIGH_MARK = 0.90        # plausibility threshold to trigger lowering
_RAPID_RISE_RATE_MIN    = 0.04        # risk_rate_per_hour to stack rapid-rise adj.
_PLAUSIBILITY_CAN_LOWER = 0.40        # below this: don't lower threshold at all

# PRE_ALERT: intermediate state between SAFE and WARNING.
# Fires when probability is below the SAFE ceiling but the prediction ring buffer
# already shows a clear upward trend (requires ≥2 prior predictions in buffer).
PRE_ALERT_PROB_FLOOR      = 0.10   # minimum prob for PRE_ALERT consideration
_PRE_ALERT_STRENGTH_MIN   = 0.30   # trend_strength minimum
_PRE_ALERT_CONFIDENCE_MIN = 0.55   # directional consistency minimum

# Additional downward DANGER threshold pressure when trend is unambiguous.
_ADJ_STRONG_TREND        = -0.04
_STRONG_TREND_STRENGTH   = 0.40
_STRONG_TREND_CONFIDENCE = 0.60


# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class ThresholdAdjustment:
    """One applied adjustment to the DANGER threshold."""
    reason: str
    delta: float  # negative = lower threshold (more sensitive), positive = raise


@dataclass
class AdaptiveClassification:
    """
    Full audit record of a single adaptive classification decision.

    Included in pipeline output under prediction.adaptive_classification so
    operators can understand exactly why a DANGER/WARNING was (or was not) issued.
    """
    risk_level: str
    probability: float
    base_danger_threshold: float
    effective_danger_threshold: float
    adjustments: list[ThresholdAdjustment] = field(default_factory=list)
    classification_basis: str = ""

    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "probability": round(self.probability, 4),
            "base_danger_threshold": self.base_danger_threshold,
            "effective_danger_threshold": self.effective_danger_threshold,
            "net_adjustment": round(
                self.effective_danger_threshold - self.base_danger_threshold, 4
            ),
            "adjustments": [
                {"reason": a.reason, "delta": round(a.delta, 4)}
                for a in self.adjustments
            ],
            "classification_basis": self.classification_basis,
        }


# ─── Thresholder ─────────────────────────────────────────────────────────────

class AdaptiveThresholder:
    """
    Context-aware risk classifier — replaces the static _classify() function.

    Reads three independent context signals before deciding the DANGER boundary:
      failure_modes    — types of failures (OOD, missing_data, signal_conflict)
      trend_state      — anomaly_detected, risk_rate_per_hour from compute_trend()
      plausibility_score — 0.0 (physically impossible) to 1.0 (realistic)

    Guard: raising adjustments (OOD, missing_data) block lowering adjustments
    to prevent paradoxical behaviour where a bad-input penalty and a
    sensitivity-increase cancel each other out.
    """

    def classify(
        self,
        probability: float,
        failure_modes: list[dict],
        trend_state: dict,
        plausibility_score: float,
    ) -> AdaptiveClassification:
        """
        Classify probability with context-adjusted DANGER threshold.

        Args:
            probability:       Raw model predict_proba score (0–1).
            failure_modes:     Failure list from detect_failures().
            trend_state:       Dict from compute_trend(); {} if no history yet.
            plausibility_score: 0–1 from score_plausibility(); default 1.0 if unavailable.

        Returns:
            AdaptiveClassification with full adjustment audit trail.
        """
        failure_types = {f.get("type", "") for f in failure_modes}
        adjustments: list[ThresholdAdjustment] = []
        danger_threshold = BASE_DANGER_THRESHOLD

        # ── Raise threshold: suspicious / incomplete input ────────────────────
        if "ood_input" in failure_types:
            adjustments.append(ThresholdAdjustment(
                reason="OOD input — sensor malfunction likely; extreme values are noise, not signal",
                delta=_ADJ_OOD_RAISE,
            ))
            danger_threshold += _ADJ_OOD_RAISE

        if "missing_data" in failure_types:
            adjustments.append(ThresholdAdjustment(
                reason="Missing data — cannot independently verify extreme conditions",
                delta=_ADJ_MISSING_RAISE,
            ))
            danger_threshold += _ADJ_MISSING_RAISE

        # ── Lower threshold: independent physical evidence of escalation ──────
        # Only allowed when input is not flagged as unreliable (OOD) and
        # plausibility is sufficient to trust the signal values.
        can_lower = (
            "ood_input" not in failure_types
            and plausibility_score >= _PLAUSIBILITY_CAN_LOWER
        )

        if can_lower:
            if trend_state.get("anomaly_detected"):
                anomaly_type = trend_state.get("anomaly_type", "unknown")
                adjustments.append(ThresholdAdjustment(
                    reason=(
                        f"Trend anomaly ({anomaly_type}) in 8-step history — "
                        "context confirms escalation pattern independent of model probability"
                    ),
                    delta=_ADJ_TREND_ANOMALY,
                ))
                danger_threshold += _ADJ_TREND_ANOMALY

                rate = float(trend_state.get("risk_rate_per_hour") or 0.0)
                if rate > _RAPID_RISE_RATE_MIN:
                    adjustments.append(ThresholdAdjustment(
                        reason=f"Rapid risk escalation rate {rate:.3f}/hr — imminent danger development window",
                        delta=_ADJ_RAPID_RISE,
                    ))
                    danger_threshold += _ADJ_RAPID_RISE

            if plausibility_score >= _PLAUSIBILITY_HIGH_MARK:
                adjustments.append(ThresholdAdjustment(
                    reason=(
                        f"High physical plausibility ({plausibility_score:.2f}) — "
                        "extreme input is physically realistic, not a sensor artifact"
                    ),
                    delta=_ADJ_HIGH_PLAUS,
                ))
                danger_threshold += _ADJ_HIGH_PLAUS

            if "signal_conflict" in failure_types:
                adjustments.append(ThresholdAdjustment(
                    reason=(
                        "Signal conflict present — rule-based baseline may be detecting danger "
                        "that the ML model undersells due to training distribution mismatch"
                    ),
                    delta=_ADJ_CONFLICT_LOWER,
                ))
                danger_threshold += _ADJ_CONFLICT_LOWER

            # Strong rising trend: unambiguous directional signal across prior predictions.
            # Requires ≥2 predictions in buffer (trend_state has meaningful data).
            ts = float(trend_state.get("trend_strength", 0.0))
            tc = float(trend_state.get("trend_confidence", 0.0))
            if (
                trend_state.get("risk_trend") == "increasing"
                and ts >= _STRONG_TREND_STRENGTH
                and tc >= _STRONG_TREND_CONFIDENCE
            ):
                adjustments.append(ThresholdAdjustment(
                    reason=(
                        f"Strong rising trend (strength={ts:.2f}, confidence={tc:.2f}) — "
                        "consistent upward trajectory across prediction history"
                    ),
                    delta=_ADJ_STRONG_TREND,
                ))
                danger_threshold += _ADJ_STRONG_TREND

        # ── Clamp to operational bounds ───────────────────────────────────────
        effective = round(
            max(_MIN_DANGER_THRESHOLD, min(_MAX_DANGER_THRESHOLD, danger_threshold)),
            4,
        )

        # ── Classify ─────────────────────────────────────────────────────────
        if probability < BASE_SAFE_THRESHOLD:
            risk_level = "SAFE"
            basis = f"prob {probability:.4f} < SAFE ceiling {BASE_SAFE_THRESHOLD:.2f} (no context adjustment applied)"
        elif probability >= effective:
            risk_level = "DANGER"
            basis = f"prob {probability:.4f} >= adjusted DANGER threshold {effective:.2f}"
        else:
            risk_level = "WARNING"
            basis = (
                f"prob {probability:.4f} in WARNING band "
                f"[{BASE_SAFE_THRESHOLD:.2f}, {effective:.2f})"
            )

        # ── Early WARNING: multi-signal physical convergence ──────────────────
        # Fires when model is still cautious (SAFE) but ≥2 prior predictions show
        # consistent upward trajectory combined with high rainfall accumulation and
        # rising water level.  Non-event single-call inputs always have data_points=0
        # → cannot satisfy _ew_dp >= 2 → zero false-alarm risk from this branch.
        if risk_level == "SAFE" and probability >= 0.12:
            _ew_ts  = float(trend_state.get("trend_strength", 0.0))
            _ew_tc  = float(trend_state.get("trend_confidence", 0.0))
            _ew_acc = float(trend_state.get("rainfall_acc_3h", 0.0))
            _ew_wld = float(trend_state.get("water_level_delta_cur", 0.0))
            _ew_dp  = int(trend_state.get("data_points", 0))
            if (
                trend_state.get("risk_trend") == "increasing"
                and _ew_ts  >= 0.35
                and _ew_tc  >= 0.65
                and _ew_acc >= 20.0
                and _ew_wld >= 0.06
                and _ew_dp  >= 2
            ):
                risk_level = "WARNING"
                basis = (
                    f"Early WARNING: multi-signal convergence — "
                    f"rising trend (strength={_ew_ts:.2f}, confidence={_ew_tc:.2f}), "
                    f"3h acc {_ew_acc:.0f}mm, water rise Δ{_ew_wld:.3f} "
                    "across ≥2 prior prediction steps"
                )

        # ── PRE_ALERT override (SAFE → PRE_ALERT when trend is rising) ────────
        # Only fires when the model sees SAFE probability but a clear upward
        # trend has been established across ≥2 prior predictions in the ring buffer.
        # Does NOT escalate WARNING/DANGER — those are already above SAFE ceiling.
        if risk_level == "SAFE" and probability >= PRE_ALERT_PROB_FLOOR:
            _ts = float(trend_state.get("trend_strength", 0.0))
            _tc = float(trend_state.get("trend_confidence", 0.0))
            if (
                trend_state.get("risk_trend") == "increasing"
                and _ts >= _PRE_ALERT_STRENGTH_MIN
                and _tc >= _PRE_ALERT_CONFIDENCE_MIN
            ):
                risk_level = "PRE_ALERT"
                basis = (
                    f"prob {probability:.4f} below SAFE ceiling {BASE_SAFE_THRESHOLD:.2f} "
                    f"but rising trend active (strength={_ts:.2f}, confidence={_tc:.2f}) "
                    "— PRE_ALERT: monitor closely, no immediate deployment"
                )

        return AdaptiveClassification(
            risk_level=risk_level,
            probability=probability,
            base_danger_threshold=BASE_DANGER_THRESHOLD,
            effective_danger_threshold=effective,
            adjustments=adjustments,
            classification_basis=basis,
        )

"""
Final Decision Engine — unified hierarchical decision authority for the flood pipeline.

Enforces strict priority order at every prediction:
  1. Physical Reality  — HydrologyAssessment SIAGA levels override ML/baseline
  2. System Integrity  — CONFLICT/LOW_TRUST trigger conservative guardrails
  3. ML + Adaptive     — calibration-aware probability × context-adjusted threshold
  4. Trend Signals     — anomalies extend the trace; WARNING + rising trend flags urgency

This is the sole decision authority. All escalation, override, and adjustment logic
terminates here. Upstream agents compute inputs; this engine makes the final call
and traces every step completely.

Public API:
    run_decision_engine(**kwargs) → DecisionResult
    write_calibration_cache(ece, brier, n) → None
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

_log = logging.getLogger(__name__)

# ─── Physical override thresholds ────────────────────────────────────────────
_HYDRO_SIAGA1_SEVERITY      = 1.00   # unconditional DANGER
_HYDRO_SIAGA2_NEAR_SEVERITY = 0.75   # DANGER when also near next threshold
_HYDRO_RAPID_SEVERITY       = 0.50   # DANGER when rapid escalation present
_HYDRO_MIN_PLAUSIBILITY     = 0.30   # below this the physical data itself is suspect

# ─── Calibration penalty ─────────────────────────────────────────────────────
_ECE_PENALTY_THRESHOLD = 0.10         # ECE above this → apply confidence penalty
_ECE_PENALTY_SCALE     = 2.00         # (ECE − threshold) × scale = fractional reduction
_ECE_MIN_MULTIPLIER    = 0.80         # never penalise more than 20%

# ─── Inconsistency detection ─────────────────────────────────────────────────
_INCONSISTENCY_HYDRO_MIN  = 0.75      # hydrology severity contradicting SAFE
_INCONSISTENCY_DELTA_MIN  = 0.08      # probability trend delta contradicting SAFE

# ─── Calibration cache path ──────────────────────────────────────────────────
_CALIBRATION_CACHE = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "artifacts", "configurations", "calibration_cache.json",
    )
)
_CALIBRATION_CACHE_MAX_AGE_DAYS = 30


@lru_cache(maxsize=1)
def _load_cached_ece() -> float:
    """
    Read last-computed ECE from cache file; returns 0.0 if absent or unreadable.

    Warns (once per process) if:
      - Cache file is missing — ECE=0.0 assumed, calibration penalty is inactive.
      - Cache is older than _CALIBRATION_CACHE_MAX_AGE_DAYS — may reflect a
        previous model version. Re-run app/evaluation/calibration.py to refresh.
    Written by app/evaluation/calibration.py (offline tool).
    """
    if not os.path.exists(_CALIBRATION_CACHE):
        _log.warning(
            "calibration_cache.json not found at %s — ECE=0.0 assumed, "
            "no calibration penalty applied. "
            "Run app/evaluation/calibration.py to generate it.",
            _CALIBRATION_CACHE,
        )
        return 0.0
    try:
        with open(_CALIBRATION_CACHE, encoding="utf-8") as fh:
            data = json.load(fh)
        written_at = data.get("written_at")
        if written_at:
            try:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(written_at)).days
                if age_days > _CALIBRATION_CACHE_MAX_AGE_DAYS:
                    _log.warning(
                        "calibration_cache.json is %d days old (model_version=%r) — "
                        "confidence penalties may reflect a stale model. "
                        "Re-run app/evaluation/calibration.py.",
                        age_days,
                        data.get("model_version", "unknown"),
                    )
            except (ValueError, TypeError):
                pass
        ece = float(data.get("ece", 0.0))
        return ece if 0.0 <= ece <= 1.0 else 0.0
    except (OSError, ValueError, KeyError):
        pass
    return 0.0


# ─── Output dataclass ────────────────────────────────────────────────────────

@dataclass
class DecisionResult:
    """
    Authoritative output of the final decision engine.
    Stored on EvaluationResult.decision and serialised by ActionAgent.
    """
    risk_level: str
    confidence_score: float
    # Which hierarchy layer made the final call:
    #   "physical_override" | "system_guardrail" | "ml_adaptive" | "trend_informed"
    decision_source: str
    decision_trace: list[str] = field(default_factory=list)
    decision_summary: str = ""
    # One-sentence human-readable explanation based on strongest active signal (Task 10).
    final_reason: str = ""
    override_trace: dict = field(default_factory=dict)
    inconsistency_check: dict = field(default_factory=dict)
    confidence_adjustment: dict = field(default_factory=dict)
    adaptive_threshold: dict = field(default_factory=dict)
    hydrology_narrative: str = ""
    scenario_comparison: dict = field(default_factory=dict)


# ─── Public entry point ───────────────────────────────────────────────────────

def run_decision_engine(
    *,
    evaluation_risk_level: str,
    adjusted_confidence: float,
    system_status: str,
    probability: float,
    raw_model_confidence: float,
    failure_modes: list[dict],
    baseline_result: dict,
    signals: dict,
    diagnostics: dict,
    hydrology_assessment,           # HydrologyAssessment | None (avoids circular import)
    plausibility_score: float = 1.0,
    has_critical_violation: bool = False,
    trust_breakdown=None,           # TrustBreakdown | None
    adaptive_classification: dict | None = None,
    calibration_ece: float | None = None,
) -> DecisionResult:
    """
    Run the hierarchical decision engine on a single pipeline output.

    Never raises — all failure modes produce a conservative fallback.

    Decision authority (highest to lowest priority):
      L0 — INVALID INPUT GUARD: has_critical_violation=True → WARNING, ML suppressed
      L1 — Physical Reality:   hydrology SIAGA + plausible data → DANGER override
      L1.5 Multi-Signal:       extreme rainfall + BMKG + compound risk → DANGER
      L2 — System Integrity:   CONFLICT/LOW_TRUST guardrails
      L3 — ML + Adaptive:      calibrated probability × adaptive threshold
      L4 — Trend Signals:      anomaly extension only (cannot create risk)
    """
    trace: list[str] = []
    risk_level = evaluation_risk_level or "WARNING"
    confidence  = float(adjusted_confidence) if adjusted_confidence is not None else 0.5

    # ── Null-safe input coercion ─────────────────────────────────────────────
    failure_modes    = failure_modes or []
    signals          = signals or {}
    diagnostics      = diagnostics or {}
    baseline_result  = baseline_result or {}
    if isinstance(plausibility_score, dict):
        plausibility_score = float(plausibility_score.get("plausibility_score", 1.0))
    else:
        plausibility_score = float(plausibility_score) if plausibility_score is not None else 1.0
    probability        = float(probability) if probability is not None else 0.0
    raw_model_confidence = float(raw_model_confidence) if raw_model_confidence is not None else confidence

    # ── Calibration ECE ──────────────────────────────────────────────────────
    if calibration_ece is None:
        calibration_ece = _load_cached_ece()
    calibration_ece = float(calibration_ece) if calibration_ece is not None else 0.0

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 0 — INVALID INPUT GUARD (HIGHEST AUTHORITY)
    # ═══════════════════════════════════════════════════════════════════════════
    # Hard architectural invariant: physically invalid inputs MUST NOT have
    # ML decision authority. When the plausibility hard gate has flagged a
    # critical violation, the ML probability is computed (for transparency
    # and trace) but is structurally barred from setting risk_level.
    #
    # Conservative fallback:
    #   risk_level   = "WARNING" — cannot trust SAFE (sensors lying); cannot
    #                  escalate to DANGER (no verified physical evidence).
    #   This matches the existing operator playbook for WARNING + LOW_TRUST +
    #   manual_review: "elevated alert, do not automate, verify in field."
    #
    # Why this layer is unbypassable:
    #   - Returns DecisionResult immediately — no later layer can re-promote risk.
    #   - decision_source = "invalid_input_fallback" — distinguishable in storage.
    #   - Trace records the suppressed ML output for auditability.
    if bool(has_critical_violation):
        l0_trace = [
            f"[L0-INVALID-INPUT] Physical impossibility detected "
            f"(plausibility_score={plausibility_score:.2f}, has_critical_violation=True). "
            f"ML output ({evaluation_risk_level}, prob={probability:.4f}) is SUPPRESSED — "
            "ML cannot have decision authority over physically invalid input.",
            "[L0-INVALID-INPUT] → Conservative fallback: risk_level=WARNING. "
            "Cannot confirm SAFE without trustworthy sensors; cannot confirm DANGER "
            "without verified physical evidence. Manual sensor verification required.",
            f"[FINAL] risk=WARNING, confidence={confidence:.4f}, "
            "source=invalid_input_fallback",
        ]
        return DecisionResult(
            risk_level="WARNING",
            confidence_score=round(confidence, 4),
            decision_source="invalid_input_fallback",
            decision_trace=l0_trace,
            decision_summary=(
                "Input failed the physical plausibility gate — ML decision authority "
                "suppressed. Conservative WARNING issued pending manual sensor verification."
            ),
            final_reason=(
                "Physically invalid sensor input detected; ML output cannot be trusted. "
                "WARNING is a conservative placeholder until field verification confirms "
                "or refutes a flood condition."
            ),
            override_trace={
                "triggered": True,
                "reason": "invalid_input_guard — has_critical_violation=True",
                "confidence": "n/a (ML suppressed)",
                "hydrology_severity": 0.0,
                "dominant_station": "",
                "dominant_siaga": "",
            },
            inconsistency_check={"detected": False, "reason": ""},
            confidence_adjustment={
                "calibration_penalty": 0.0,
                "calibration_ece": round(calibration_ece, 4),
                "applied": False,
                "reason": "calibration not applied — ML output suppressed by L0 guard",
                "final_confidence": round(confidence, 4),
            },
            adaptive_threshold={},
            hydrology_narrative="",
            scenario_comparison={},
        )

    # ── Hydrology fields (safe attribute access) ─────────────────────────────
    hydro_severity = float(getattr(hydrology_assessment, "severity_score", 0.0) or 0.0)
    hydro_dominant = str(getattr(hydrology_assessment, "dominant_station", "") or "")
    hydro_siaga    = str(getattr(hydrology_assessment, "dominant_siaga_level", "normal") or "normal")
    hydro_near     = int(getattr(hydrology_assessment, "near_threshold_count", 0) or 0)
    hydro_rapid    = bool(getattr(hydrology_assessment, "rapid_escalation", False))
    hydro_expl     = str(getattr(hydrology_assessment, "overall_explanation", "") or "")
    hydro_stations = list(getattr(hydrology_assessment, "stations", []) or [])

    # ── Trend fields (safe access — diagnostics already coerced to dict) ─────
    trend_state   = diagnostics.get("trend_state") or {}
    risk_trend    = str(trend_state.get("risk_trend") or "stable")
    risk_delta    = float(trend_state.get("risk_delta_1h") or 0.0)
    rate_per_hour = float(trend_state.get("risk_rate_per_hour") or 0.0)
    wl_trend      = str(trend_state.get("water_level_trend") or "stable")
    anomaly_type  = trend_state.get("anomaly_type")

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 1 — Physical Reality Override
    # ═══════════════════════════════════════════════════════════════════════════
    physical_override   = False
    override_reason     = ""
    override_confidence = "low"

    if plausibility_score >= _HYDRO_MIN_PLAUSIBILITY:
        if hydro_severity >= _HYDRO_SIAGA1_SEVERITY:
            physical_override   = True
            override_reason     = (
                f"{hydro_dominant} at {hydro_siaga.upper()} "
                f"(severity={hydro_severity:.2f}) — critical water level "
                "confirmed by BPBD operational thresholds"
            )
            override_confidence = "high"
        elif hydro_severity >= _HYDRO_SIAGA2_NEAR_SEVERITY and hydro_near > 0:
            physical_override   = True
            override_reason     = (
                f"{hydro_dominant} at {hydro_siaga.upper()} with "
                f"{hydro_near} station(s) approaching next alert level — "
                "near-threshold imminent escalation"
            )
            override_confidence = "medium"
        elif hydro_rapid and hydro_severity >= _HYDRO_RAPID_SEVERITY:
            physical_override   = True
            override_reason     = (
                f"Rapid hydrological escalation at {hydro_dominant} — "
                "rapid water level rise with elevated siaga status"
            )
            override_confidence = "medium"

    if physical_override:
        risk_level      = "DANGER"
        decision_source = "physical_override"
        trace.append(
            f"[L1-PHYSICAL] {hydro_dominant} {hydro_siaga.upper()} "
            f"(severity={hydro_severity:.2f}) overrides ML output ({evaluation_risk_level})"
        )
        trace.append(
            f"[L1-PHYSICAL] → Risk escalated to DANGER "
            f"(physical confidence: {override_confidence})"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 1.5 — Extreme Multi-Signal Override
    # Triggers when physical sensors (L1) didn't fire but extreme compound conditions
    # are independently confirmed: extreme rainfall + BMKG Extreme/confirmed alert +
    # compound risk all active simultaneously, with plausible input data.
    # This catches events where station SIAGA data isn't available in real-time but
    # the atmospheric + BMKG signals confirm an extreme event.
    # ═══════════════════════════════════════════════════════════════════════════
    elif (
        plausibility_score >= 0.70
        and signals.get("extreme_rainfall")
        and signals.get("bmkg_confirmed")
        and signals.get("compound_risk")
        and risk_level in ("SAFE", "WARNING")
    ):
        risk_level      = "DANGER"
        decision_source = "signal_override"
        trace.append(
            "[L1.5-SIGNAL] Extreme rainfall + BMKG confirmed + compound risk "
            f"active simultaneously (plausibility={plausibility_score:.2f}) — "
            f"overrides ML output ({evaluation_risk_level})"
        )
        trace.append(
            "[L1.5-SIGNAL] → Risk escalated to DANGER "
            "(multi-signal extreme event, physical station data unavailable)"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 2 — System Integrity Guardrails
    # ═══════════════════════════════════════════════════════════════════════════
    elif system_status in ("CONFLICT", "LOW_TRUST"):
        decision_source = "system_guardrail"
        if risk_level == "SAFE":
            # Only escalate SAFE→WARNING when positive flood signals exist and data is
            # plausible enough to trust. Pure data-absence failures (missing_data, ood_input
            # with low plausibility) should not manufacture WARNING from nothing.
            _positive_flood_signals = (
                "extreme_rainfall", "high_rainfall", "sustained_rainfall",
                "critical_water_level", "high_water_level", "rising_water",
                "rapid_rise", "bmkg_extreme", "bmkg_confirmed", "compound_risk",
                "hydro_stress",
            )
            _has_flood_signal = any(signals.get(k) for k in _positive_flood_signals)
            if _has_flood_signal and plausibility_score >= 0.40:
                risk_level = "WARNING"
                trace.append(
                    f"[L2-GUARDRAIL] {system_status} — positive flood signals present "
                    f"(plausibility={plausibility_score:.2f}), SAFE escalated to WARNING"
                )
            else:
                trace.append(
                    f"[L2-GUARDRAIL] {system_status} — no positive flood signals or "
                    f"low plausibility ({plausibility_score:.2f}), SAFE retained"
                )
        else:
            trace.append(
                f"[L2-GUARDRAIL] {system_status} — ML result ({risk_level}) retained "
                "with reduced confidence; manual verification required"
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 3 — ML + Adaptive Threshold
    # ═══════════════════════════════════════════════════════════════════════════
    else:
        decision_source = "ml_adaptive"
        trace.append(
            f"[L3-ML] probability={probability:.4f} → {risk_level} "
            f"(system: {system_status}, confidence: {confidence:.4f})"
        )
        if adaptive_classification:
            eff = adaptive_classification.get("effective_danger_threshold", 0.45)
            net = float(adaptive_classification.get("net_adjustment", 0.0))
            if abs(net) > 0.001:
                direction = "lowered" if net < 0 else "raised"
                trace.append(
                    f"[L3-ML] Adaptive threshold {direction} by {net:+.3f} "
                    f"to {eff:.3f} — context-adjusted classification"
                )
            else:
                trace.append(
                    f"[L3-ML] Base threshold {eff:.3f} unchanged — no context adjustments"
                )

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 3.5 — Signal Conflict Conservative Escalation
    # When ML says SAFE but a signal_conflict failure is active alongside BMKG
    # extreme/confirmed alerts, the competing signals indicate genuine uncertainty
    # that warrants at least WARNING. Applies only when data is plausible.
    # ═══════════════════════════════════════════════════════════════════════════
    if (
        risk_level == "SAFE"
        and any(f.get("type") == "signal_conflict" for f in failure_modes)
        and (signals.get("bmkg_confirmed") or signals.get("bmkg_extreme"))
        and plausibility_score >= 0.70
    ):
        risk_level      = "WARNING"
        decision_source = "signal_override"
        trace.append(
            "[L3.5-CONFLICT] signal_conflict + BMKG confirmed/extreme — "
            "competing evidence warrants conservative WARNING (plausibility="
            f"{plausibility_score:.2f})"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # PLAUSIBILITY GATE — Suppress ML escalation on implausible inputs
    # When input data is highly implausible (IsolationForest flagged extreme outlier),
    # any ML-derived WARNING/DANGER is likely caused by the impossible values
    # themselves (e.g., 650 mm/h rain, humidity=200%) rather than real flood conditions.
    # Physical overrides and multi-signal overrides bypass this gate — they use
    # station-level and BMKG data that is independently validated.
    # ═══════════════════════════════════════════════════════════════════════════
    if (
        plausibility_score < _HYDRO_MIN_PLAUSIBILITY
        and risk_level != "SAFE"
        and decision_source not in ("physical_override", "signal_override")
    ):
        risk_level = "SAFE"
        trace.append(
            f"[PLAUSIBILITY-GATE] plausibility={plausibility_score:.2f} < "
            f"{_HYDRO_MIN_PLAUSIBILITY} — ML escalation suppressed, "
            "SAFE retained (OOD inputs cannot drive confident flood prediction)"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # LAYER 4 — Trend & Plausibility Signals (trace-only; non-escalating)
    # ═══════════════════════════════════════════════════════════════════════════
    if risk_trend == "increasing":
        trace.append(
            f"[L4-TREND] Risk probability increasing "
            f"(Δ={risk_delta:+.4f}, rate={rate_per_hour:+.4f}/hr) — heightened vigilance"
        )
        if risk_level == "WARNING" and decision_source == "ml_adaptive":
            decision_source = "trend_informed"
            trace.append(
                "[L4-TREND] WARNING + increasing trend → "
                "advise pre-emptive escalation readiness"
            )
    elif risk_trend == "decreasing" and risk_level != "SAFE":
        trace.append(
            f"[L4-TREND] Risk decreasing (Δ={risk_delta:+.4f}) — "
            "conditions improving but current alert level maintained"
        )

    if anomaly_type:
        anomaly_desc = (
            "sudden probability spike — possible flash flood or dam release"
            if anomaly_type == "spike"
            else "sustained monotone increase — slow-developing flood accumulation"
        )
        trace.append(
            f"[L4-TREND] Anomaly detected: {anomaly_type} — {anomaly_desc}"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Calibration Confidence Penalty
    # ═══════════════════════════════════════════════════════════════════════════
    calibration_penalty = 0.0
    calibration_reason  = "No calibration data available — confidence unchanged"
    calibration_applied = False

    if calibration_ece > _ECE_PENALTY_THRESHOLD:
        excess     = calibration_ece - _ECE_PENALTY_THRESHOLD
        multiplier = max(_ECE_MIN_MULTIPLIER, 1.0 - excess * _ECE_PENALTY_SCALE)
        original   = confidence
        confidence = round(confidence * multiplier, 4)
        calibration_penalty = round(original - confidence, 4)
        calibration_reason  = (
            f"ECE={calibration_ece:.3f} exceeds threshold {_ECE_PENALTY_THRESHOLD} — "
            "model shows calibration overconfidence under current conditions"
        )
        calibration_applied = True
        trace.append(
            f"[CALIBRATION] ECE={calibration_ece:.3f} → confidence penalised "
            f"by {calibration_penalty:.4f} (×{multiplier:.3f})"
        )
    else:
        trace.append(
            f"[CALIBRATION] ECE={calibration_ece:.3f} ≤ {_ECE_PENALTY_THRESHOLD} — "
            "model calibration acceptable, no adjustment applied"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Cross-Layer Inconsistency Detection
    # ═══════════════════════════════════════════════════════════════════════════
    inconsistency_detected = False
    inconsistency_reason   = ""

    # Inconsistency check only runs on plausible data.
    # If the input itself is OOD (plausibility < _HYDRO_MIN_PLAUSIBILITY), the
    # physical signals (hydro_severity, wl_trend) come from the same implausible
    # source and cannot be used to override a SAFE prediction. Applying the same
    # threshold as the L1 physical override gate keeps these two checks consistent.
    if risk_level == "SAFE" and plausibility_score >= _HYDRO_MIN_PLAUSIBILITY:
        if hydro_severity >= _INCONSISTENCY_HYDRO_MIN:
            inconsistency_detected = True
            inconsistency_reason   = (
                f"ML predicts SAFE but {hydro_dominant} is at "
                f"{hydro_siaga.upper()} (severity={hydro_severity:.2f})"
            )
        elif risk_delta > _INCONSISTENCY_DELTA_MIN:
            inconsistency_detected = True
            inconsistency_reason   = (
                "ML predicts SAFE but risk probability is strongly increasing "
                f"(Δ={risk_delta:+.4f})"
            )
        elif wl_trend == "rising" and hydro_severity > 0.0:
            inconsistency_detected = True
            inconsistency_reason   = (
                "ML predicts SAFE but water levels are rising "
                "with non-zero hydrology severity"
            )

    if inconsistency_detected:
        trace.append(f"[INCONSISTENCY] Detected: {inconsistency_reason}")
        # Physical evidence contradicts ML SAFE — escalate rather than just log.
        # risk_level is SAFE here (guaranteed by the outer check above).
        risk_level      = "WARNING"
        decision_source = "inconsistency_override"
        trace.append(
            "[INCONSISTENCY-OVERRIDE] Physical signal contradicts ML SAFE — "
            "risk escalated to WARNING; manual verification required"
        )

    # Final trace entry
    trace.append(
        f"[FINAL] risk={risk_level}, confidence={confidence:.4f}, "
        f"source={decision_source}"
    )

    final_reason = _build_final_reason(
        risk_level=risk_level,
        decision_source=decision_source,
        hydro_dominant=hydro_dominant,
        hydro_siaga=hydro_siaga,
        hydro_severity=hydro_severity,
        system_status=system_status,
        risk_trend=risk_trend,
        anomaly_type=anomaly_type,
        inconsistency_detected=inconsistency_detected,
        calibration_applied=calibration_applied,
        calibration_ece=calibration_ece,
    )

    return DecisionResult(
        risk_level=risk_level,
        confidence_score=round(confidence, 4),
        decision_source=decision_source,
        decision_trace=trace,
        decision_summary=_build_decision_summary(
            risk_level, decision_source, confidence, system_status,
            hydro_dominant, hydro_siaga,
        ),
        final_reason=final_reason,
        override_trace={
            "triggered": physical_override,
            "reason": override_reason if physical_override else "",
            "confidence": override_confidence if physical_override else "n/a",
            "hydrology_severity": round(hydro_severity, 4),
            "dominant_station": hydro_dominant,
            "dominant_siaga": hydro_siaga,
        },
        inconsistency_check={
            "detected": inconsistency_detected,
            "reason": inconsistency_reason if inconsistency_detected else "",
        },
        confidence_adjustment={
            "calibration_penalty": round(calibration_penalty, 4),
            "calibration_ece": round(calibration_ece, 4),
            "applied": calibration_applied,
            "reason": calibration_reason,
            "final_confidence": round(confidence, 4),
        },
        adaptive_threshold=_format_adaptive_threshold(adaptive_classification),
        hydrology_narrative=_build_hydrology_narrative(
            hydro_expl, hydro_stations, trend_state
        ),
        scenario_comparison=_build_scenario_comparison(
            confidence, raw_model_confidence, baseline_result
        ),
    )


# ─── Private helpers ──────────────────────────────────────────────────────────

def _build_decision_summary(
    risk_level: str,
    decision_source: str,
    confidence: float,
    system_status: str,
    hydro_dominant: str,
    hydro_siaga: str,
) -> str:
    if decision_source == "physical_override":
        label = (
            f"{hydro_dominant} ({hydro_siaga.upper()})"
            if hydro_dominant
            else "monitoring station"
        )
        return (
            f"Physical flood conditions at {label} override the ML model — "
            "immediate protective action is required regardless of computational confidence."
        )
    if decision_source == "system_guardrail":
        return (
            f"System integrity is {system_status.lower().replace('_', '-')} — "
            f"risk conservatively classified as {risk_level} "
            "pending independent manual verification."
        )
    if risk_level == "DANGER":
        return (
            f"Multiple independent hazard signals converge on flood danger "
            f"({confidence:.0%} confidence) — immediate protective action required."
        )
    if risk_level == "WARNING":
        return (
            f"Elevated flood risk conditions detected ({confidence:.0%} confidence) — "
            "increase monitoring cadence and activate contingency preparations."
        )
    return (
        f"No active flood threat detected across all monitored channels "
        f"({confidence:.0%} confidence) — routine monitoring is appropriate."
    )


def _format_adaptive_threshold(adaptive_cls: dict | None) -> dict:
    if not adaptive_cls:
        return {
            "danger_threshold": 0.45,
            "base_threshold": 0.45,
            "net_adjustment": 0.0,
            "adjustment_factors": [],
            "classification_basis": "Default static threshold — no context signals available",
        }
    return {
        "danger_threshold": adaptive_cls.get("effective_danger_threshold", 0.45),
        "base_threshold": adaptive_cls.get("base_danger_threshold", 0.45),
        "net_adjustment": float(adaptive_cls.get("net_adjustment", 0.0)),
        "adjustment_factors": [
            a.get("reason", "") for a in adaptive_cls.get("adjustments", [])
        ],
        "classification_basis": adaptive_cls.get("classification_basis", ""),
    }


def _build_hydrology_narrative(
    overall_explanation: str,
    stations: list,
    trend_state: dict,
) -> str:
    if not overall_explanation:
        return (
            "Hydrology data unavailable — physical conditions "
            "cannot be independently assessed."
        )
    parts = [overall_explanation]

    wl_trend = trend_state.get("water_level_trend", "stable")
    if wl_trend == "rising":
        parts.append("Water levels are trending upward across recent observations.")
    elif wl_trend == "falling":
        parts.append(
            "Water levels are declining, suggesting improving hydrological conditions."
        )

    near_stations = [s for s in stations if getattr(s, "near_threshold", False)]
    if near_stations:
        names = ", ".join(
            getattr(s, "station_name", "unknown") for s in near_stations[:2]
        )
        parts.append(
            f"Alert: {names} approaching next alert threshold — "
            "escalation possible within the current prediction window."
        )

    return " ".join(parts)


def _build_scenario_comparison(
    final_confidence: float,
    raw_model_confidence: float,
    baseline_result: dict,
) -> dict:
    """
    Quantify what each pipeline layer contributes versus simpler baselines.

    agentic_system_score : full pipeline after all adjustments
    model_only_score     : raw ML confidence before agentic penalties
    baseline_only_score  : rule-based estimate credibility (1 − disagreement)
    """
    baseline_disagreement = float(baseline_result.get("baseline_disagreement") or 0.0)
    baseline_score        = round(max(0.0, 1.0 - min(baseline_disagreement, 1.0)), 4)
    improvement           = round(final_confidence - raw_model_confidence, 4)

    return {
        "agentic_system_score": round(final_confidence, 4),
        "model_only_score": round(raw_model_confidence, 4),
        "baseline_only_score": baseline_score,
        "agentic_improvement_over_model": improvement,
        "interpretation": (
            "agentic_system_score reflects all pipeline adjustments "
            "(failure penalties, calibration, trust); "
            "model_only_score is raw ML confidence before agentic layers; "
            "baseline_only_score is rule-based estimate agreement (1 − disagreement)."
        ),
    }


def _build_final_reason(
    *,
    risk_level: str,
    decision_source: str,
    hydro_dominant: str,
    hydro_siaga: str,
    hydro_severity: float,
    system_status: str,
    risk_trend: str,
    anomaly_type,
    inconsistency_detected: bool,
    calibration_applied: bool,
    calibration_ece: float,
) -> str:
    """
    One-sentence human-readable reason based on the single strongest active signal.

    Priority: physical override > inconsistency > system guardrail >
              anomaly > trend > calibration > normal assessment.
    """
    if decision_source == "physical_override":
        label = f"{hydro_dominant} ({hydro_siaga.upper()})" if hydro_dominant else "a monitoring station"
        return (
            f"Physical water-level measurements at {label} "
            f"(severity {hydro_severity:.2f}) override the ML model and mandate DANGER classification."
        )
    if inconsistency_detected:
        return (
            "Inconsistency detected: the ML model predicts SAFE but physical and trend signals "
            "show active hazard — treat as WARNING until manually verified."
        )
    if decision_source == "system_guardrail":
        return (
            f"System integrity is {system_status.lower().replace('_', '-')} — "
            "risk classification is conservative until independent verification is complete."
        )
    if anomaly_type == "spike":
        return (
            "A sudden probability spike was detected, consistent with a flash flood or dam release — "
            f"current {risk_level} classification reflects this short-window hazard."
        )
    if anomaly_type == "monotone_increase":
        return (
            "A sustained probability increase indicates slow flood accumulation — "
            f"{risk_level} classification maintained with heightened monitoring cadence."
        )
    if risk_trend == "increasing" and risk_level == "WARNING":
        return (
            "Risk probability is actively increasing — WARNING issued with pre-emptive escalation "
            "readiness advised before conditions reach DANGER threshold."
        )
    if calibration_applied:
        return (
            f"Model confidence reduced by calibration penalty (ECE={calibration_ece:.3f}) — "
            f"final {risk_level} assessment reflects adjusted, more conservative confidence."
        )
    if risk_level == "DANGER":
        return "Multiple hazard signals converge on flood danger — immediate protective action required."
    if risk_level == "WARNING":
        return "Elevated flood risk detected — increase monitoring and activate contingency preparations."
    return "All monitored signals are within normal range — no active flood threat detected."


def failsafe_decision(
    evaluation_risk_level: str = "WARNING",
    adjusted_confidence: float = 0.5,
    error_message: str = "",
) -> DecisionResult:
    """
    Return a conservative DecisionResult when run_decision_engine() raises unexpectedly.

    Never called in healthy operation — exists purely as a crash-safety net.
    """
    reason = "Decision engine failsafe activated"
    if error_message:
        reason = f"{reason}: {error_message}"
    # SAFE is never acceptable on the failsafe path — the engine may have crashed
    # mid-escalation, so the pre-crash risk could be lower than the true answer.
    # DANGER is preserved (already the highest level). WARNING and SAFE both become WARNING.
    _failsafe_risk = "DANGER" if evaluation_risk_level == "DANGER" else "WARNING"
    return DecisionResult(
        risk_level=_failsafe_risk,
        confidence_score=min(float(adjusted_confidence), 0.5),
        decision_source="system_guardrail",
        decision_trace=[f"[FAILSAFE] {reason}"],
        decision_summary=(
            "Decision engine encountered an internal error — "
            "conservative risk classification applied. Manual review required."
        ),
        final_reason=reason,
        override_trace={"triggered": False, "reason": reason, "confidence": "n/a"},
        inconsistency_check={"detected": False, "reason": ""},
        confidence_adjustment={"applied": False, "reason": reason},
        adaptive_threshold={},
        hydrology_narrative="",
        scenario_comparison={},
    )


def write_calibration_cache(
    ece: float, brier: float = 0.0, n: int = 0, model_version: str = "unknown"
) -> None:
    """
    Persist the latest ECE so the decision engine can apply a runtime confidence
    penalty when the model is poorly calibrated. Called by calibration.py.

    Writes: ece, brier, n, model_version, written_at (ISO 8601 UTC).
    written_at and model_version are used by _load_cached_ece() to warn on staleness.
    """
    try:
        os.makedirs(os.path.dirname(_CALIBRATION_CACHE), exist_ok=True)
        with open(_CALIBRATION_CACHE, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "ece": round(ece, 6),
                    "brier": round(brier, 6),
                    "n": n,
                    "model_version": model_version,
                    "written_at": datetime.now(timezone.utc).isoformat(),
                },
                fh,
            )
        _load_cached_ece.cache_clear()
    except OSError:
        pass

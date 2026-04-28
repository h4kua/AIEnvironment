"""
PerceptionAgent — Stage 1 of the agentic flood decision pipeline.

Responsibility: parse and validate the raw snapshot dict, assess data
freshness and structural completeness, and identify which signal categories
(rainfall, hydrology, BMKG) are actually present in the current observation.

Explicitly does NOT make risk decisions — that belongs to ReasoningAgent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.bnpb_context import VulnerabilityContext, get_vulnerability_context
from app.services.hydrology_analyzer import HydrologyAssessment, analyze_hydrology
from app.services.plausibility_check import score_plausibility


@dataclass
class PerceptionResult:
    """Structured output of PerceptionAgent. Passed directly to ReasoningAgent."""

    snapshot: dict
    openweather: dict
    poskobanjir: list
    bmkg_alerts: list
    # Minutes since snapshot was fetched; -1.0 if timestamp absent or unparseable.
    data_freshness_minutes: float
    # Fraction of expected top-level sections present (0.0–1.0).
    snapshot_completeness: float
    # Which signal categories are detectable from the current snapshot.
    signal_presence: dict
    # Raw scalars extracted directly from snapshot (before the feature builder runs).
    raw_features: dict
    # Physical plausibility score 0.0–1.0 from score_plausibility().
    plausibility_score: float = 1.0
    # Per-station hydrology assessment from analyze_hydrology().
    hydrology_assessment: HydrologyAssessment = field(default_factory=HydrologyAssessment)
    # Non-blocking issues noted during parsing. No risk decisions made here.
    perception_warnings: list[str] = field(default_factory=list)
    # Long-term regional vulnerability from BNPB InaRISK (NOT real-time).
    # None when BNPB API is unavailable or district cannot be matched.
    # MUST NOT influence probability or risk_level — affects only manual_review
    # threshold and recommended_action priority.
    vulnerability_context: Optional[VulnerabilityContext] = field(default=None)
    # District mapping audit trail from get_vulnerability_context().
    # Always present so ActionAgent can surface it regardless of whether
    # vulnerability_context is None (failed/low-confidence mapping).
    mapping_info: dict = field(default_factory=dict)


class PerceptionAgent:
    """
    Stage 1: Perception.

    Parses the raw JSON snapshot and answers three structural questions:
      1. How fresh is this data?
      2. Which required sections are present?
      3. Which physical signal categories are detectable?

    All output is factual and descriptive — no risk judgement is made here.
    """

    _EXPECTED_SECTIONS = ("fetched_at_utc", "openweather", "poskobanjir", "bmkg_alerts")

    def run(self, snapshot: dict) -> PerceptionResult:
        warnings: list[str] = []

        openweather = snapshot.get("openweather") or {}
        poskobanjir = snapshot.get("poskobanjir") or []
        bmkg_alerts = snapshot.get("bmkg_alerts") or []

        freshness = self._compute_freshness(snapshot, warnings)
        completeness = self._compute_completeness(snapshot)
        signal_presence = self._assess_signal_presence(openweather, poskobanjir, bmkg_alerts)
        raw_features = self._extract_raw_features(openweather, poskobanjir, bmkg_alerts)
        # score_plausibility returns a dict; extract the float here so
        # PerceptionResult.plausibility_score is always a proper float as typed.
        # Storing the raw dict previously forced downstream agents to carry a
        # defensive dict-branch — fixing at the source removes that ambiguity.
        plausibility_dict  = score_plausibility(snapshot)
        plausibility_float = float(plausibility_dict.get("plausibility_score", 1.0))
        hydrology = analyze_hydrology(poskobanjir)

        # BNPB InaRISK vulnerability context — silently None on any failure.
        # Derive district from snapshot["location"] if set, else fall back to
        # OpenWeatherMap city name. No default "Jakarta" — ambiguous inputs
        # correctly return (None, mapping_info) from the mapping function.
        district = (
            snapshot.get("location")
            or (openweather.get("name") if openweather else None)
            or ""
        )
        # get_vulnerability_context always returns a 2-tuple:
        #   (VulnerabilityContext | None, mapping_info dict)
        # mapping_info is always populated for transparency output even when
        # vuln_context is None (low confidence, stale data, API down).
        vuln_context, mapping_info = get_vulnerability_context(str(district))

        return PerceptionResult(
            snapshot=snapshot,
            openweather=openweather,
            poskobanjir=poskobanjir,
            bmkg_alerts=bmkg_alerts,
            data_freshness_minutes=freshness,
            snapshot_completeness=completeness,
            signal_presence=signal_presence,
            raw_features=raw_features,
            plausibility_score=plausibility_float,
            hydrology_assessment=hydrology,
            perception_warnings=warnings,
            vulnerability_context=vuln_context,
            mapping_info=mapping_info,
        )

    def _compute_freshness(self, snapshot: dict, warnings: list[str]) -> float:
        fetched_at = snapshot.get("fetched_at_utc")
        if not fetched_at:
            warnings.append("Missing fetched_at_utc — data freshness unknown.")
            return -1.0
        try:
            dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
        except (ValueError, TypeError):
            warnings.append(f"Cannot parse fetched_at_utc: {fetched_at!r}")
            return -1.0

    def _compute_completeness(self, snapshot: dict) -> float:
        present = sum(1 for s in self._EXPECTED_SECTIONS if snapshot.get(s) is not None)
        return round(present / len(self._EXPECTED_SECTIONS), 4)

    def _assess_signal_presence(self, ow: dict, posko: list, bmkg: list) -> dict:
        main = ow.get("main") or {}
        rain = ow.get("rain") or {}
        return {
            "has_temperature": bool(main.get("temp")),
            "has_humidity": bool(main.get("humidity")),
            "has_rainfall_1h": "1h" in rain,
            "has_rainfall_3h": "3h" in rain,
            "has_water_levels": len(posko) > 0,
            "has_bmkg_alerts": len(bmkg) > 0,
            "posko_record_count": len(posko),
            "bmkg_alert_count": len(bmkg),
        }

    def _extract_raw_features(self, ow: dict, posko: list, bmkg: list) -> dict:
        main = ow.get("main") or {}
        rain = ow.get("rain") or {}
        return {
            "temperature_c": main.get("temp"),
            "humidity_pct": main.get("humidity"),
            "rainfall_1h_mm": rain.get("1h", 0.0),
            "rainfall_3h_mm": rain.get("3h", 0.0),
            "bmkg_alert_count": len(bmkg),
            "water_level_records": len(posko),
        }

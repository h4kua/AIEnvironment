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
    plausibility: dict = field(default_factory=dict)
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
    _NORMALIZED_DELTA_KEYS = ("water_level_delta", "water_level_delta_cur")
    _PREVIOUS_LEVEL_KEYS = (
        "previous_tinggi_air",
        "tinggi_air_prev",
        "tinggi_air_previous",
        "previous_height_cm",
        "prev_height_cm",
        "height_cm_prev",
    )
    _HISTORY_KEYS = ("ketinggian", "height_cm_history", "water_level_history")

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
        water_level_delta = self._extract_water_level_delta(snapshot, poskobanjir)
        hydrology = analyze_hydrology(
            poskobanjir,
            water_level_delta=water_level_delta,
        )

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
            plausibility=plausibility_dict,
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

    def _extract_water_level_delta(self, snapshot: dict, posko: list) -> float | None:
        for container in (snapshot, snapshot.get("diagnostics") or {}):
            if not isinstance(container, dict):
                continue
            for key in self._NORMALIZED_DELTA_KEYS:
                delta = self._safe_float(container.get(key))
                if delta is not None:
                    return delta

        deltas = [
            delta
            for delta in (self._station_water_level_delta(record) for record in posko)
            if delta is not None
        ]
        if not deltas:
            return None
        return round(max(deltas), 4)

    def _station_water_level_delta(self, record: dict) -> float | None:
        for key in self._NORMALIZED_DELTA_KEYS:
            delta = self._safe_float(record.get(key))
            if delta is not None:
                return delta

        current_level = self._safe_float(record.get("tinggi_air"))
        if current_level is None:
            return None

        previous_level = None
        for key in self._PREVIOUS_LEVEL_KEYS:
            previous_level = self._safe_float(record.get(key))
            if previous_level is not None:
                break

        if previous_level is None:
            history = self._extract_numeric_series(record)
            if len(history) >= 2:
                previous_level = history[-2]
                current_level = history[-1]

        if previous_level is None:
            return None

        reference = self._reference_threshold(record)
        if reference is None or reference <= 0:
            return None

        return round((current_level - previous_level) / reference, 4)

    def _extract_numeric_series(self, record: dict) -> list[float]:
        for key in self._HISTORY_KEYS:
            raw = record.get(key)
            if raw in ("", None):
                continue
            values = raw if isinstance(raw, list) else str(raw).split(",")
            series: list[float] = []
            for value in values:
                parsed = self._safe_float(value)
                if parsed is not None:
                    series.append(parsed)
            if len(series) >= 2:
                return series
        return []

    def _reference_threshold(self, record: dict) -> float | None:
        thresholds = [
            value
            for value in (
                self._safe_float(record.get("siaga1")),
                self._safe_float(record.get("siaga2")),
                self._safe_float(record.get("siaga3")),
                self._safe_float(record.get("siaga4")),
            )
            if value is not None and value > 0
        ]
        if not thresholds:
            return None
        return max(thresholds)

    def _safe_float(self, value: object) -> float | None:
        try:
            if value in ("", None):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

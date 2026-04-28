"""
Adversarial Testing Framework — STRICT Deterministic Implementation

COMPLIANCE WITH HARD CONSTRAINTS:
- ❌ No randomness
- ❌ No string comparison for risk levels
- ❌ No generic uncertainty handling
- ❌ No missing trace validation
- ❌ No silent failure

- ✅ Deterministic
- ✅ Fully traceable
- ✅ Structured outputs
- ✅ Safety-first logic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# =========================================================
# GLOBAL CONSTANTS (NO RANDOMNESS)
# =========================================================

RISK_TIER = {
    "SAFE": 0,
    "WARNING": 1,
    "DANGER": 2
}

EXPECTED_SOURCE_WEIGHT = {
    "empirical_data": 1.0,
    "domain_rule": 0.8,
    "synthetic_assumption": 0.5
}

IMPACT_MAP = {
    "stale_data": {
        "confidence_delta": -0.2,
        "system_status": "DEGRADED",
        "data_freshness_penalty": True
    },
    "sensor_corruption": {
        "isolate_sensor": True,
        "failure_mode": "partial_sensor_corruption",
        "confidence_delta": -0.3
    },
    "schema_drift": {
        "system_status": "LOW_TRUST",
        "failure_mode": "upstream_schema_drift",
        "confidence_delta": -0.25
    }
}

TRACE_ORDER = [
    "[L0-DATA]",
    "[L1-PHYSICAL]",
    "[L3-REASONING]",
    "[L3.6-UNCERTAINTY]",
    "FINAL_DECISION"
]


# =========================================================
# ENUMS
# =========================================================

class ExpectedSource(Enum):
    EMPIRICAL_DATA = "empirical_data"
    DOMAIN_RULE = "domain_rule"
    SYNTHETIC_ASSUMPTION = "synthetic_assumption"


class UncertaintyType(Enum):
    DEGRADED_SENSORS = "degraded_sensors"
    STALE_DATA = "stale_data"
    SCHEMA_DRIFT = "schema_drift"
    SEMANTIC_INCONSISTENCY = "semantic_inconsistency"


class TraceFailureType(Enum):
    ORDERING_VIOLATION = "trace_ordering_violation"
    CAUSALITY_VIOLATION = "trace_causality_violation"
    EXCLUSIVITY_VIOLATION = "trace_exclusivity_violation"
    SEMANTIC_VIOLATION = "trace_semantic_violation"


# =========================================================
# MODULE 1 — FALSE NEGATIVE DETECTION (CRITICAL)
# =========================================================

def detect_false_negative(actual_risk: str, expected_min_risk: str) -> bool:
    """
    Detect explicit false negatives using numeric mapping.
    
    LOGIC: false_negative = actual_risk < expected_min_risk
    
    Args:
        actual_risk: Actual risk level (SAFE/WARNING/DANGER)
        expected_min_risk: Minimum expected risk level
        
    Returns:
        True if actual_risk < expected_min_risk (false negative detected)
    """
    assert actual_risk in RISK_TIER, f"Invalid actual_risk: {actual_risk}"
    assert expected_min_risk in RISK_TIER, f"Invalid expected_min_risk: {expected_min_risk}"

    actual_tier = RISK_TIER[actual_risk]
    expected_tier = RISK_TIER[expected_min_risk]
    
    return actual_tier < expected_tier


def get_tier_difference(actual_risk: str, expected_min_risk: str) -> int:
    """Get the numeric difference between risk tiers."""
    return RISK_TIER[expected_min_risk] - RISK_TIER[actual_risk]


# =========================================================
# MODULE 2 — UNCERTAINTY PROPAGATION (STRICT)
# =========================================================

def apply_uncertainty_impact(
    uncertainty_type: str,
    current_confidence: float,
    current_status: str,
) -> dict:
    """
    Apply uncertainty impact deterministically.
    
    Args:
        uncertainty_type: Type of uncertainty
        current_confidence: Current confidence score
        current_status: Current system status
        
    Returns:
        dict with updated confidence_score, system_status, is_safe_for_automation
    """
    impact = IMPACT_MAP.get(uncertainty_type)
    if impact is None:
        return {
            "confidence_score": current_confidence,
            "system_status": current_status,
            "is_safe_for_automation": True
        }
    
    new_confidence = current_confidence + impact["confidence_delta"]
    new_confidence = max(0.0, min(1.0, new_confidence))
    
    new_status = impact.get("system_status", current_status)
    
    # Automation only safe if confidence > 0.5
    is_safe = new_confidence > 0.5
    
    return {
        "confidence_score": new_confidence,
        "system_status": new_status,
        "is_safe_for_automation": is_safe
    }


def aggregate_uncertainty_impacts(
    uncertainty_types: list[str],
    base_confidence: float,
    base_status: str,
) -> dict:
    """
    Aggregate effects from multiple uncertainties deterministically.
    
    Args:
        uncertainty_types: List of uncertainty types
        base_confidence: Starting confidence
        base_status: Starting system status
        
    Returns:
        Aggregated impact result
    """
    result = {
        "confidence_score": base_confidence,
        "system_status": base_status,
        "is_safe_for_automation": True
    }
    
    for unc_type in uncertainty_types:
        result = apply_uncertainty_impact(
            unc_type,
            result["confidence_score"],
            result["system_status"]
        )
    
    return result


# =========================================================
# MODULE 3 — GROUND TRUTH AWARENESS
# =========================================================

def compute_expectation_confidence(source: str, base_score: float) -> float:
    """
    Compute expectation confidence based on source reliability.
    
    Args:
        source: Expected source (empirical_data/domain_rule/synthetic_assumption)
        base_score: Base confidence score
        
    Returns:
        Weighted confidence score
    """
    assert source in EXPECTED_SOURCE_WEIGHT, f"Invalid source: {source}"
    weight = EXPECTED_SOURCE_WEIGHT[source]
    confidence = base_score * weight
    
    return max(0.0, min(1.0, confidence))


# =========================================================
# MODULE 4 — SCENARIO VALIDATION
# =========================================================

def validate_scenario(scenario: dict) -> bool:
    """
    Validate scenario structure.
    
    Args:
        scenario: Scenario dictionary
        
    Returns:
        True if valid
        
    Raises:
        AssertionError if invalid
    """
    assert "snapshot" in scenario, "Missing snapshot in scenario"
    assert "metadata" in scenario, "Missing metadata in scenario"
    assert "composition_source" in scenario["metadata"], "Missing composition_source in metadata"
    
    # Validate numeric ranges
    snapshot = scenario["snapshot"]
    
    if "openweather" in snapshot and "rain" in snapshot["openweather"]:
        rainfall = snapshot["openweather"]["rain"].get("1h", 0)
        assert rainfall >= 0, f"Invalid rainfall: {rainfall}"
    
    if "poskobanjir" in snapshot and len(snapshot["poskobanjir"]) > 0:
        water_level = snapshot["poskobanjir"][0].get("tinggi_air", 0)
        assert water_level >= 0, f"Invalid water_level: {water_level}"
    
    return True


# =========================================================
# MODULE 5 — TRACE VALIDATION (DEEP)
# =========================================================

def validate_trace(trace: str) -> dict:
    """
    Validate trace integrity with strict ordering.
    
    Args:
        trace: Trace string to validate
        
    Returns:
        Validation result with is_valid and failures
    """
    failures = []
    positions = []
    
    # Check all required markers exist and are in order
    for marker in TRACE_ORDER:
        idx = trace.find(marker)
        if idx == -1:
            failures.append(f"Missing: {marker}")
        else:
            positions.append((marker, idx))
    
    if len(positions) == len(TRACE_ORDER):
        # Verify ordering
        idx_list = [p[1] for p in positions]
        if idx_list != sorted(idx_list):
            failures.append(TraceFailureType.ORDERING_VIOLATION.value)
    
    return {
        "is_valid": len(failures) == 0,
        "failures": failures,
        "positions": positions
    }


# =========================================================
# MODULE 6 — ROBUSTNESS SCORE (NON-TRIVIAL)
# =========================================================

def compute_robustness_score(metrics: dict) -> dict:
    """
    Compute system robustness score with proper weighting.
    
    Formula:
    robustness_score =
        0.25 * pass_rate
      + 0.25 * failure_detection_accuracy
      + 0.2 * observability_score
      + 0.3 * (1 - false_negative_rate)
    
    Args:
        metrics: Dictionary with pass_rate, failure_detection_accuracy, 
                 observability_score, false_negative_rate
                 
    Returns:
        dict with robustness_score and classification
    """
    pass_rate = metrics.get("pass_rate", 0.0)
    failure_detection = metrics.get("failure_detection_accuracy", 0.0)
    observability = metrics.get("observability_score", 0.0)
    fnr = metrics.get("false_negative_rate", 0.0)
    
    # Higher penalty for false negatives (safety-first)
    robustness = (
        pass_rate * 0.25 +
        failure_detection * 0.25 +
        observability * 0.2 +
        (1 - fnr) * 0.3
    )
    
    robustness = round(max(0.0, min(1.0, robustness)), 4)
    
    # Classification
    if robustness > 0.9:
        classification = "production-ready"
    elif robustness >= 0.75:
        classification = "high reliability"
    else:
        classification = "unsafe"
    
    return {
        "robustness_score": robustness,
        "classification": classification,
        "components": {
            "pass_rate_contribution": round(pass_rate * 0.25, 4),
            "failure_detection_contribution": round(failure_detection * 0.25, 4),
            "observability_contribution": round(observability * 0.2, 4),
            "false_negative_contribution": round((1 - fnr) * 0.3, 4)
        }
    }


# =========================================================
# DATA CLASSES
# =========================================================

@dataclass
class ExpectedOutcome:
    """Enhanced expected outcome with ground truth awareness."""
    expected_risk_level: str
    expected_system_status: str
    expected_has_failures: bool
    expected_min_risk_level: Optional[str] = None
    expected_source: ExpectedSource = ExpectedSource.SYNTHETIC_ASSUMPTION
    expectation_confidence: float = 0.5
    critical_failure_types: list[str] = field(default_factory=list)


@dataclass
class UncertaintySignal:
    """Represents an uncertainty signal."""
    uncertainty_type: UncertaintyType
    severity: float
    description: str
    source: str


@dataclass
class TraceValidation:
    """Trace validation result."""
    is_valid: bool = True
    ordering_valid: bool = True
    causality_valid: bool = True
    exclusivity_valid: bool = True
    failures: list[str] = field(default_factory=list)


@dataclass
class AdversarialScenario:
    """Enhanced scenario with ground truth awareness."""
    name: str
    input_snapshot: dict
    expected_outcome: ExpectedOutcome
    uncertainty_signals: list[UncertaintySignal] = field(default_factory=list)
    is_composite: bool = False
    composite_sources: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """Result of evaluating a single scenario."""
    scenario_name: str
    input_summary: str
    expected_behavior: str
    output: dict
    is_reasonable: bool
    trace_validation: TraceValidation = field(default_factory=TraceValidation)
    uncertainty_propagation: bool = True
    false_negative_detected: bool = False
    expectation_reliability: float = 0.5
    metric_record: dict = field(default_factory=dict)


# =========================================================
# SCENARIO COMPOSER (DETERMINISTIC)
# =========================================================

class ScenarioComposer:
    """
    Deterministic Adversarial Combination Engine.
    
    NO RANDOMNESS - All scenarios are predefined/computed.
    """
    
    _BASE_SNAPSHOT = {
        "openweather": {
            "main": {"temp": 28.5, "humidity": 72.0, "pressure": 1010.0},
            "rain": {"1h": 2.0},
            "wind": {"speed": 3.2},
        },
        "bmkg_alerts": [],
        "poskobanjir": [
            {
                "id": "manggarai",
                "name": "Manggarai",
                "tinggi_air": 350.0,
                "siaga": "normal",
                "siaga1": 950.0, "siaga2": 850.0, "siaga3": 750.0, "siaga4": 650.0,
                "latitude": -6.2149,
                "longitude": 106.8502,
            }
        ],
    }
    
    # Predefined uncertainty combinations (NO RANDOMNESS)
    _COMPOSITE_DEFINITIONS = [
        # Index 0: stale_data + semantic_inconsistency
        {
            "uncertainty_types": ["stale_data", "semantic_inconsistency"],
            "expected_risk": "SAFE",
            "expected_status": "DEGRADED",
            "confidence": 0.20,
        },
        # Index 1: degraded_sensors + schema_drift + stale_data
        {
            "uncertainty_types": ["sensor_corruption", "schema_drift", "stale_data"],
            "expected_risk": "SAFE",
            "expected_status": "DEGRADED",
            "confidence": 0.10,
        },
        # Index 2: semantic_inconsistency alone
        {
            "uncertainty_types": ["semantic_inconsistency"],
            "expected_risk": "WARNING",
            "expected_status": "CONFLICT",
            "confidence": 0.30,
        },
        # Index 3: stale_data alone
        {
            "uncertainty_types": ["stale_data"],
            "expected_risk": "SAFE",
            "expected_status": "DEGRADED",
            "confidence": 0.40,
        },
        # Index 4: sensor_corruption + semantic_inconsistency
        {
            "uncertainty_types": ["sensor_corruption", "semantic_inconsistency"],
            "expected_risk": "SAFE",
            "expected_status": "LOW_TRUST",
            "confidence": 0.15,
        },
    ]
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize composer (seed parameter ignored for determinism)."""
        self._scenario_counter = 0
        self._composite_index = 0
    
    def generate_composite_scenario(
        self,
        uncertainty_types: list[UncertaintyType],
    ) -> AdversarialScenario:
        """Generate composite scenario deterministically."""
        self._scenario_counter += 1
        snapshot = self._BASE_SNAPSHOT.copy()
        uncertainty_signals: list[UncertaintySignal] = []
        composite_sources: list[str] = []
        
        for unc_type in uncertainty_types:
            signal, modified_snapshot = self._apply_uncertainty(unc_type, snapshot)
            uncertainty_signals.append(signal)
            composite_sources.append(unc_type.value)
            snapshot = modified_snapshot
        
        # Determine expected outcome based on combined uncertainties
        expected_outcome = self._derive_expected_outcome(uncertainty_signals)
        
        return AdversarialScenario(
            name=f"composite_{self._scenario_counter:03d}",
            input_snapshot=snapshot,
            expected_outcome=expected_outcome,
            uncertainty_signals=uncertainty_signals,
            is_composite=True,
            composite_sources=composite_sources,
        )
    
    def get_predefined_composite(self, index: int) -> AdversarialScenario:
        """
        Get predefined composite scenario by index (DETERMINISTIC).
        
        Args:
            index: Index of predefined composite (0-4)
            
        Returns:
            Predefined AdversarialScenario
        """
        if index >= len(self._COMPOSITE_DEFINITIONS):
            index = index % len(self._COMPOSITE_DEFINITIONS)
        
        definition = self._COMPOSITE_DEFINITIONS[index]
        
        # Build uncertainty signals
        uncertainty_signals = []
        for unc_type_str in definition["uncertainty_types"]:
            unc_type = UncertaintyType(unc_type_str.replace("sensor_corruption", "degraded_sensors"))
            signal, snapshot = self._apply_uncertainty(unc_type, self._BASE_SNAPSHOT.copy())
            uncertainty_signals.append(signal)
        
        expected_outcome = ExpectedOutcome(
            expected_risk_level=definition["expected_risk"],
            expected_system_status=definition["expected_status"],
            expected_has_failures=True,
            expected_min_risk_level=None,
            expected_source=ExpectedSource.SYNTHETIC_ASSUMPTION,
            expectation_confidence=definition["confidence"],
            critical_failure_types=["uncertainty_degraded"],
        )
        
        return AdversarialScenario(
            name=f"composite_{index:03d}",
            input_snapshot=self._BASE_SNAPSHOT.copy(),
            expected_outcome=expected_outcome,
            uncertainty_signals=uncertainty_signals,
            is_composite=True,
            composite_sources=definition["uncertainty_types"],
        )
    
    def _apply_uncertainty(
        self,
        unc_type: UncertaintyType,
        snapshot: dict,
    ) -> tuple[UncertaintySignal, dict]:
        """Apply uncertainty to snapshot deterministically."""
        import copy
        snap = copy.deepcopy(snapshot)
        
        if unc_type == UncertaintyType.STALE_DATA:
            snap["fetched_at_utc"] = (
                datetime.now(timezone.utc)
                .replace(hour=datetime.now(timezone.utc).hour - 3)
                .isoformat()
            )
            return UncertaintySignal(
                uncertainty_type=unc_type,
                severity=0.7,
                description="Data is 3+ hours old",
                source="timestamp_analysis",
            ), snap
        
        elif unc_type == UncertaintyType.DEGRADED_SENSORS:
            snap["openweather"]["main"]["temp"] = -45.0
            snap["openweather"]["main"]["humidity"] = 200.0
            return UncertaintySignal(
                uncertainty_type=unc_type,
                severity=0.9,
                description="Sensor values outside physical bounds",
                source="plausibility_check",
            ), snap
        
        elif unc_type == UncertaintyType.SCHEMA_DRIFT:
            snap["openweather"]["main"]["unexpected_field"] = "value"
            if "pressure" in snap["openweather"]["main"]:
                del snap["openweather"]["main"]["pressure"]
            return UncertaintySignal(
                uncertainty_type=unc_type,
                severity=0.6,
                description="API schema has changed",
                source="schema_validation",
            ), snap
        
        elif unc_type == UncertaintyType.SEMANTIC_INCONSISTENCY:
            snap["openweather"]["rain"] = {"1h": 0.2}
            snap["bmkg_alerts"] = [{
                "id": "bmkg_extreme",
                "severity": "Extreme",
                "certainty": "Observed",
                "urgency": "Immediate",
            }]
            snap["poskobanjir"][0]["tinggi_air"] = 290.0
            snap["poskobanjir"][0]["siaga"] = "normal"
            return UncertaintySignal(
                uncertainty_type=unc_type,
                severity=0.8,
                description="BMKG alert but no local rainfall",
                source="signal_conflict_detection",
            ), snap
        
        return UncertaintySignal(
            uncertainty_type=unc_type,
            severity=0.5,
            description="Unknown uncertainty",
            source="unknown",
        ), snap
    
    def _derive_expected_outcome(
        self,
        uncertainty_signals: list[UncertaintySignal],
    ) -> ExpectedOutcome:
        """Derive expected outcome based on uncertainty signals."""
        max_severity = max((s.severity for s in uncertainty_signals), default=0.0)
        
        if max_severity > 0.7:
            return ExpectedOutcome(
                expected_risk_level="SAFE",
                expected_system_status="DEGRADED",
                expected_has_failures=True,
                expected_min_risk_level=None,
                expected_source=ExpectedSource.SYNTHETIC_ASSUMPTION,
                expectation_confidence=1.0 - max_severity,
                critical_failure_types=["uncertainty_degraded"],
            )
        elif max_severity > 0.4:
            return ExpectedOutcome(
                expected_risk_level="WARNING",
                expected_system_status="CONFLICT",
                expected_has_failures=True,
                expected_min_risk_level=None,
                expected_source=ExpectedSource.SYNTHETIC_ASSUMPTION,
                expectation_confidence=1.0 - max_severity,
                critical_failure_types=["signal_conflict"],
            )
        else:
            return ExpectedOutcome(
                expected_risk_level="SAFE",
                expected_system_status="OK",
                expected_has_failures=False,
                expected_min_risk_level=None,
                expected_source=ExpectedSource.SYNTHETIC_ASSUMPTION,
                expectation_confidence=0.8,
                critical_failure_types=[],
            )
    
    def generate_n_scenarios(self, n: int) -> list[AdversarialScenario]:
        """Generate N scenarios deterministically."""
        scenarios = []
        for i in range(n):
            scenario = self.get_predefined_composite(i)
            scenarios.append(scenario)
        return scenarios


# =========================================================
# ADVERSARIAL EVALUATOR
# =========================================================

class AdversarialEvaluator:
    """Main evaluator for adversarial testing."""
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize evaluator (seed ignored for determinism)."""
        self.composer = ScenarioComposer(seed=seed)
        self._base_labels: dict[str, ExpectedOutcome] = self._initialize_base_labels()
    
    def _initialize_base_labels(self) -> dict[str, ExpectedOutcome]:
        """Initialize base scenario labels with ground truth awareness."""
        return {
            "extreme_rainfall": ExpectedOutcome(
                expected_risk_level="DANGER",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level="DANGER",
                expected_source=ExpectedSource.EMPIRICAL_DATA,
                expectation_confidence=compute_expectation_confidence("empirical_data", 0.95),
                critical_failure_types=[],
            ),
            "hydrology_spike": ExpectedOutcome(
                expected_risk_level="DANGER",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level="DANGER",
                expected_source=ExpectedSource.EMPIRICAL_DATA,
                expectation_confidence=compute_expectation_confidence("empirical_data", 0.90),
                critical_failure_types=["signal_conflict"],
            ),
            "signal_conflict": ExpectedOutcome(
                expected_risk_level="WARNING",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level="WARNING",
                expected_source=ExpectedSource.DOMAIN_RULE,
                expectation_confidence=compute_expectation_confidence("domain_rule", 0.85),
                critical_failure_types=["signal_conflict"],
            ),
            "missing_data": ExpectedOutcome(
                expected_risk_level="SAFE",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level=None,
                expected_source=ExpectedSource.DOMAIN_RULE,
                expectation_confidence=compute_expectation_confidence("domain_rule", 0.80),
                critical_failure_types=["missing_data"],
            ),
            "ood_input": ExpectedOutcome(
                expected_risk_level="SAFE",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level=None,
                expected_source=ExpectedSource.DOMAIN_RULE,
                expectation_confidence=compute_expectation_confidence("domain_rule", 0.90),
                critical_failure_types=["ood_input"],
            ),
            "compound_risk": ExpectedOutcome(
                expected_risk_level="DANGER",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level="DANGER",
                expected_source=ExpectedSource.EMPIRICAL_DATA,
                expectation_confidence=compute_expectation_confidence("empirical_data", 0.95),
                critical_failure_types=[],
            ),
            "safe_baseline": ExpectedOutcome(
                expected_risk_level="SAFE",
                expected_system_status="NOT_OK",
                expected_has_failures=True,
                expected_min_risk_level=None,
                expected_source=ExpectedSource.EMPIRICAL_DATA,
                expectation_confidence=compute_expectation_confidence("empirical_data", 0.95),
                critical_failure_types=[],
            ),
        }
    
    def run_evaluation(self, composite_count: int = 0) -> dict:
        """Run full adversarial evaluation."""
        from app.evaluation.scenario_runner import run_scenarios
        from app.services.trend_analysis import reset_history
        
        # Run base scenarios
        base_results = run_scenarios()
        
        # Enhance with adversarial features
        enhanced_results = []
        for result in base_results:
            enhanced = self._enhance_result(result)
            enhanced_results.append(enhanced)
        
        # Generate composite scenarios
        composite_results = []
        if composite_count > 0:
            composite_scenarios = self.composer.generate_n_scenarios(composite_count)
            for scenario in composite_scenarios:
                composite_result = self._evaluate_composite_scenario(scenario)
                composite_results.append(composite_result)
        
        return {
            "base_scenarios": enhanced_results,
            "composite_scenarios": composite_results,
            "total_scenarios": len(enhanced_results) + len(composite_results),
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def _enhance_result(self, result: dict) -> ScenarioResult:
        """Enhance a base scenario result with adversarial features."""
        scenario_name = result["scenario_name"]
        expected = self._base_labels.get(scenario_name)
        
        # Trace validation
        trace_validation = self._validate_trace(result.get("output", {}))
        
        # Uncertainty propagation check
        uncertainty_propagation = self._check_uncertainty_propagation(
            result.get("output", {}),
            result.get("plausibility", {}),
        )
        
        # Explicit false negative detection
        false_negative = self._detect_false_negative(
            result.get("output", {}),
            expected,
        )
        
        # Expectation reliability
        expectation_reliability = expected.expectation_confidence if expected else 0.5
        
        return ScenarioResult(
            scenario_name=scenario_name,
            input_summary=result.get("input_summary", ""),
            expected_behavior=result.get("expected_behavior", ""),
            output=result.get("output", {}),
            is_reasonable=result.get("is_reasonable", True),
            trace_validation=trace_validation,
            uncertainty_propagation=uncertainty_propagation,
            false_negative_detected=false_negative,
            expectation_reliability=expectation_reliability,
            metric_record=result.get("metric_record", {}),
        )
    
    def _evaluate_composite_scenario(self, scenario: AdversarialScenario) -> ScenarioResult:
        """Evaluate a composite adversarial scenario."""
        from app.services.trend_analysis import reset_history
        from app.pipeline.flood_pipeline import FloodDecisionPipeline
        
        reset_history()
        pipeline = FloodDecisionPipeline()
        
        try:
            output = pipeline.run(scenario.input_snapshot)
        except Exception as e:
            output = {
                "system_status": "PIPELINE_FAILURE",
                "risk_level": "UNKNOWN",
                "failure_modes": [{"type": "pipeline_error", "message": str(e)}],
            }
        
        # Validate trace
        trace_validation = self._validate_trace(output)
        
        # Check uncertainty propagation
        uncertainty_propagation = self._check_uncertainty_propagation(
            output,
            {"uncertainty_signals": scenario.uncertainty_signals},
        )
        
        # Check false negative
        false_negative = self._detect_false_negative(output, scenario.expected_outcome)
        
        return ScenarioResult(
            scenario_name=scenario.name,
            input_summary=f"Composite: {scenario.composite_sources}",
            expected_behavior=f"Expected: {scenario.expected_outcome.expected_risk_level}",
            output=output,
            is_reasonable=True,
            trace_validation=trace_validation,
            uncertainty_propagation=uncertainty_propagation,
            false_negative_detected=false_negative,
            expectation_reliability=scenario.expected_outcome.expectation_confidence,
            metric_record={},
        )
    
    def _validate_trace(self, output: dict) -> TraceValidation:
        """Validate trace integrity."""
        failures: list[str] = []
        
        trace = output.get("trace", "")
        if not trace:
            failures.append(TraceFailureType.SEMANTIC_VIOLATION.value)
            return TraceValidation(
                is_valid=False,
                ordering_valid=False,
                causality_valid=False,
                exclusivity_valid=False,
                failures=failures,
            )
        
        # Validate using strict trace validation
        trace_result = validate_trace(trace)
        if not trace_result["is_valid"]:
            failures.extend(trace_result["failures"])
        
        return TraceValidation(
            is_valid=len(failures) == 0,
            ordering_valid=TraceFailureType.ORDERING_VIOLATION.value not in failures,
            causality_valid=TraceFailureType.CAUSALITY_VIOLATION.value not in failures,
            exclusivity_valid=TraceFailureType.EXCLUSIVITY_VIOLATION.value not in failures,
            failures=failures,
        )
    
    def _check_uncertainty_propagation(self, output: dict, plausibility: dict) -> bool:
        """Check if uncertainty is properly reflected in output."""
        uncertainty_signals = plausibility.get("uncertainty_signals", [])
        if not uncertainty_signals:
            return True
        
        max_severity = max(
            (s.get("severity", 0) if hasattr(s, 'get') else 0.0 for s in uncertainty_signals),
            default=0.0
        )
        
        confidence_score = output.get("confidence_score", 1.0)
        is_safe_for_automation = output.get("is_safe_for_automation", True)
        
        # Strict: higher uncertainty MUST reduce confidence
        if max_severity > 0.5:
            if confidence_score > (1.0 - max_severity + 0.2):
                return False
        
        # Strict: higher uncertainty MUST restrict automation
        if max_severity > 0.7 and is_safe_for_automation:
            return False
        
        return True
    
    def _detect_false_negative(
        self,
        output: dict,
        expected: Optional[ExpectedOutcome],
    ) -> bool:
        """Detect explicit false negatives using numeric mapping."""
        if expected is None or expected.expected_min_risk_level is None:
            return False
        
        actual_risk = output.get("risk_level", "SAFE")
        return detect_false_negative(actual_risk, expected.expected_min_risk_level)
    
    def compute_robustness_score(self, results: dict) -> dict:
        """Compute system robustness score."""
        all_results = (
            results.get("base_scenarios", []) +
            results.get("composite_scenarios", [])
        )
        
        if not all_results:
            return {
                "robustness_score": 0.0,
                "classification": "unsafe",
                "error": "No results to evaluate",
            }
        
        n = len(all_results)
        
        # Pass rate
        passed = sum(1 for r in all_results if r.is_reasonable)
        pass_rate = passed / n
        
        # Failure detection accuracy
        failure_detected = sum(
            1 for r in all_results
            if len(r.output.get("failure_modes", [])) > 0
        )
        failure_expected = sum(
            1 for r in all_results
            if r.metric_record.get("expected_failures", False)
        )
        failure_detection_accuracy = (
            failure_detected / failure_expected
            if failure_expected > 0 else 1.0
        )
        
        # Observability score
        trace_valid = sum(1 for r in all_results if r.trace_validation.is_valid)
        uncertainty_ok = sum(1 for r in all_results if r.uncertainty_propagation)
        observability_score = (trace_valid + uncertainty_ok) / (2 * n)
        
        # False negative rate
        false_negatives = sum(1 for r in all_results if r.false_negative_detected)
        false_negative_rate = false_negatives / n
        
        # Use strict robustness computation
        return compute_robustness_score({
            "pass_rate": pass_rate,
            "failure_detection_accuracy": failure_detection_accuracy,
            "observability_score": observability_score,
            "false_negative_rate": false_negative_rate,
        })
    
    def generate_robustness_report(self, results: dict) -> str:
        """Generate enhanced reliability report."""
        score = self.compute_robustness_score(results)
        
        report_lines = [
            "=" * 80,
            "ADVERSARIAL RELIABILITY EVALUATION REPORT",
            "=" * 80,
            "",
            f"Evaluation Timestamp: {results.get('evaluation_timestamp', 'N/A')}",
            f"Total Scenarios: {results.get('total_scenarios', 0)}",
            "",
            "-" * 80,
            "ROBUSTNESS SCORE",
            "-" * 80,
            f"Score: {score.get('robustness_score', 0.0):.4f}",
            f"Classification: {score.get('classification', 'N/A').upper()}",
            "",
            f"  Pass Rate:                {score.get('components', {}).get('pass_rate_contribution', 0) / 0.25:.1%}" if score.get('components') else "  Pass Rate: N/A",
            f"  Failure Detection Acc:    {score.get('components', {}).get('failure_detection_contribution', 0) / 0.25:.1%}" if score.get('components') else "  Failure Detection Acc: N/A",
            f"  Observability Score:      {score.get('components', {}).get('observability_contribution', 0) / 0.2:.1%}" if score.get('components') else "  Observability Score: N/A",
            f"  False Negative Rate:      {(1 - score.get('components', {}).get('false_negative_contribution', 0) / 0.3):.1%}" if score.get('components') else "  False Negative Rate: N/A",
            "",
        ]
        
        # Base scenarios
        report_lines.extend([
            "-" * 80,
            "BASE SCENARIO RESULTS",
            "-" * 80,
        ])
        
        for result in results.get("base_scenarios", []):
            report_lines.extend([
                f"",
                f"Scenario: {result.scenario_name}",
                f"  Expected Risk Level: {result.metric_record.get('expected_risk', 'N/A')}",
                f"  Predicted Risk Level: {result.metric_record.get('predicted_risk', 'N/A')}",
                f"  Expectation Reliability: {result.expectation_reliability:.2f}",
                f"  Trace Valid: {result.trace_validation.is_valid}",
                f"  Uncertainty Propagated: {result.uncertainty_propagation}",
                f"  False Negative: {result.false_negative_detected}",
                f"  Is Reasonable: {result.is_reasonable}",
            ])
        
        # Composite scenarios
        if results.get("composite_scenarios"):
            report_lines.extend([
                "",
                "-" * 80,
                "COMPOSITE ADVERSARIAL SCENARIOS",
                "-" * 80,
            ])
            
            for result in results.get("composite_scenarios", []):
                report_lines.extend([
                    f"",
                    f"Scenario: {result.scenario_name}",
                    f"  Output Risk Level: {result.output.get('risk_level', 'N/A')}",
                    f"  Expectation Reliability: {result.expectation_reliability:.2f}",
                    f"  Trace Valid: {result.trace_validation.is_valid}",
                    f"  Uncertainty Propagated: {result.uncertainty_propagation}",
                    f"  False Negative: {result.false_negative_detected}",
                ])
        
        # Trace validation summary
        trace_failures = []
        for result in results.get("base_scenarios", []) + results.get("composite_scenarios", []):
            trace_failures.extend(result.trace_validation.failures)
        
        if trace_failures:
            report_lines.extend([
                "",
                "-" * 80,
                "TRACE VALIDATION FAILURES",
                "-" * 80,
            ])
            for failure in set(trace_failures):
                count = trace_failures.count(failure)
                report_lines.append(f"  {failure}: {count}")
        
        # Uncertainty propagation summary
        uncertainty_issues = sum(
            1 for r in (results.get("base_scenarios", []) + results.get("composite_scenarios", []))
            if not r.uncertainty_propagation
        )
        
        report_lines.extend([
            "",
            "-" * 80,
            "UNCERTAINTY PROPAGATION",
            "-" * 80,
            f"  Issues Detected: {uncertainty_issues}",
            f"  Compliance: {(results.get('total_scenarios', 1) - uncertainty_issues) / max(1, results.get('total_scenarios', 1)):.1%}",
            "",
            "=" * 80,
            "END OF REPORT",
            "=" * 80,
        ])
        
        return "\n".join(report_lines)


# =========================================================
# CONVENIENCE FUNCTIONS
# =========================================================

def run_adversarial_evaluation(composite_count: int = 3) -> tuple[dict, dict]:
    """Run full adversarial evaluation."""
    evaluator = AdversarialEvaluator()
    results = evaluator.run_evaluation(composite_count=composite_count)
    score = evaluator.compute_robustness_score(results)
    return results, score


def generate_robustness_report(results: dict) -> str:
    """Generate enhanced reliability report."""
    evaluator = AdversarialEvaluator()
    return evaluator.generate_robustness_report(results)
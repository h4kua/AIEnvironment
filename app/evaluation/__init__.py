"""
Evaluation Module — Adversarial Testing Framework

Exports:
- AdversarialEvaluator: Main evaluator for adversarial testing
- ScenarioComposer: Adversarial combination engine
- ExpectedOutcome: Enhanced expected outcome with ground truth awareness
- ExpectedSource: Source of ground truth expectation
- UncertaintyType: Types of input uncertainty signals
- TraceFailureType: Types of trace validation failures
- run_adversarial_evaluation: Convenience function
- generate_robustness_report: Report generator
"""

from app.evaluation.adversarial_framework import (
    AdversarialEvaluator,
    ScenarioComposer,
    ExpectedOutcome,
    ExpectedSource,
    UncertaintyType,
    TraceFailureType,
    AdversarialScenario,
    ScenarioResult,
    TraceValidation,
    UncertaintySignal,
    run_adversarial_evaluation,
    generate_robustness_report,
)

# Also export existing components for backward compatibility
from app.evaluation.metrics import (
    SCENARIO_LABELS,
    ScenarioLabel,
    compute_classification_metrics,
    aggregate_evaluation_report,
)

from app.evaluation.scenario_runner import run_scenarios

__all__ = [
    # New adversarial framework
    "AdversarialEvaluator",
    "ScenarioComposer",
    "ExpectedOutcome",
    "ExpectedSource",
    "UncertaintyType",
    "TraceFailureType",
    "AdversarialScenario",
    "ScenarioResult",
    "TraceValidation",
    "UncertaintySignal",
    "run_adversarial_evaluation",
    "generate_robustness_report",
    # Existing components
    "SCENARIO_LABELS",
    "ScenarioLabel",
    "compute_classification_metrics",
    "aggregate_evaluation_report",
    "run_scenarios",
]
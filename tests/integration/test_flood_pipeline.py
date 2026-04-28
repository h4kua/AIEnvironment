"""
Smoke test for FloodDecisionPipeline end-to-end output structure.

Verifies that the pipeline returns a structurally valid response with all
required top-level keys, regardless of the current snapshot values.

The module is self-contained: if a live snapshot is not present at
``DEFAULT_REALTIME_SNAPSHOT``, the autouse fixture below writes a minimal
Jakarta-normal-range snapshot for the duration of the test module and
removes it on teardown. Live snapshots produced by the data ingestion
pipeline are detected and left untouched.
"""
import json
from datetime import datetime, timezone

import pytest

from app.pipeline.flood_pipeline import FloodDecisionPipeline
from app.utils.paths import DEFAULT_REALTIME_SNAPSHOT

_REQUIRED_KEYS = {
    "risk_level",
    "probability",
    "confidence_score",
    "requires_manual_review",
    "dominant_risk_driver",
    "risk_interpretation",
    "recommended_action",
    "failure_modes",
    "pipeline_version",
    "pipeline_execution_ms",
    "_decision_authority",
}

_VALID_RISK_LEVELS = {"SAFE", "WARNING", "DANGER", "UNKNOWN"}


def _minimal_snapshot() -> dict:
    """Synthetic snapshot in Jakarta normal operational range."""
    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "location": "Jakarta Selatan",
        "openweather": {
            "name": "Jakarta",
            "main": {"temp": 30.0, "humidity": 80.0, "pressure": 1010.0},
            "rain": {"1h": 2.0, "3h": 6.0},
            "wind": {"speed": 3.0},
        },
        "poskobanjir": [
            {
                "id": "manggarai",
                "name": "Manggarai",
                "tinggi_air": 300.0,
                "siaga1": 950.0,
                "siaga2": 850.0,
                "siaga3": 750.0,
                "siaga4": 650.0,
            }
        ],
        "bmkg_alerts": [],
    }


@pytest.fixture(scope="module", autouse=True)
def _provision_realtime_snapshot():
    """
    Ensure the snapshot file exists; remove only files this fixture created.

    Handles a checked-in artefact in this repo: ``poskobanjir/data/clean`` and
    ``poskobanjir/data/raw`` exist in the working tree as empty 0-byte files
    (probably from a botched ``touch`` during initial checkout). Production
    code would have these as directories. The fixture upgrades the empty
    placeholder to a directory on the fly so the pipeline can write its JSON.
    """
    path = DEFAULT_REALTIME_SNAPSHOT
    created_here = False
    placeholders_promoted: list = []

    if not path.exists():
        parent = path.parent
        # Walk up the chain of intended directories that exist as empty files
        # and replace them with real directories. We never touch non-empty files.
        chain: list = []
        cursor = parent
        while cursor != cursor.parent:
            if cursor.exists() and not cursor.is_dir():
                if cursor.stat().st_size == 0:
                    chain.append(cursor)
                else:
                    break  # non-empty file — refuse to clobber
            cursor = cursor.parent
        for stray in chain:
            stray.unlink()
            placeholders_promoted.append(stray)

        try:
            parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_minimal_snapshot(), fh, indent=2)
        created_here = True

    yield

    if created_here and path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    # Restore the empty-file placeholders we promoted, so the working tree
    # state matches the original checkout.
    for stray in placeholders_promoted:
        try:
            if stray.exists() and stray.is_dir():
                # Only remove if empty — never delete a directory with content.
                try:
                    stray.rmdir()
                except OSError:
                    continue
            stray.touch()
        except OSError:
            pass


def test_pipeline_returns_required_keys():
    result = FloodDecisionPipeline().run_from_file()
    missing = _REQUIRED_KEYS - result.keys()
    assert not missing, f"Pipeline output missing keys: {missing}"


def test_pipeline_risk_level_is_valid():
    result = FloodDecisionPipeline().run_from_file()
    assert result["risk_level"] in _VALID_RISK_LEVELS


def test_pipeline_probability_is_bounded():
    result = FloodDecisionPipeline().run_from_file()
    assert 0.0 <= result["probability"] <= 1.0


def test_pipeline_confidence_score_is_bounded():
    result = FloodDecisionPipeline().run_from_file()
    assert 0.0 <= result["confidence_score"] <= 1.0


def test_pipeline_decision_authority_is_evaluation_agent():
    result = FloodDecisionPipeline().run_from_file()
    assert result["_decision_authority"] == "EvaluationAgent"


def test_pipeline_version_is_agentic():
    result = FloodDecisionPipeline().run_from_file()
    assert result["pipeline_version"] == "agentic-v2.0"

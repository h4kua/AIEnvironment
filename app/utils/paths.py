from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REPORTS_DIR = ARTIFACTS_DIR / "reports"
CONFIG_DIR = ARTIFACTS_DIR / "configurations"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
POSKOBANJIR_DIR = PROJECT_ROOT / "poskobanjir"
POSKOBANJIR_CLEAN_DIR = POSKOBANJIR_DIR / "data" / "clean"
DEFAULT_REALTIME_SNAPSHOT = POSKOBANJIR_CLEAN_DIR / "realtime_snapshot.json"

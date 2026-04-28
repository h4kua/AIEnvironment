import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from app.realtime_native.feature_builder import (
    REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    REALTIME_NATIVE_FEATURES,
    build_bootstrap_training_dataset,
)
from app.utils.paths import MODELS_DIR, REPORTS_DIR


REALTIME_NATIVE_MODEL_PATH = MODELS_DIR / "flood_model_realtime_native.pkl"
REALTIME_NATIVE_SCALER_PATH = MODELS_DIR / "scaler_realtime_native.pkl"
REALTIME_NATIVE_FEATURE_LIST_PATH = MODELS_DIR / "feature_list_realtime_native.json"
REALTIME_NATIVE_MODEL_CARD_PATH = MODELS_DIR / "model_card_realtime_native.json"
REALTIME_NATIVE_OOD_PATH = MODELS_DIR / "ood_detector_realtime_native.pkl"
REALTIME_NATIVE_REPORT_PATH = REPORTS_DIR / "realtime_native_model_report.json"


def train_realtime_native_model(dataset_path=REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH):
    if not Path(dataset_path).exists():
        build_bootstrap_training_dataset(output_path=dataset_path)

    df = pd.read_csv(dataset_path)
    X = df[REALTIME_NATIVE_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = pd.to_numeric(df["banjir"], errors="coerce").fillna(0).astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    base_model = XGBClassifier(
        n_estimators=120,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
    )
    calibrated_model = CalibratedClassifierCV(base_model, method="sigmoid", cv=3)
    calibrated_model.fit(X_train_scaled, y_train)

    train_pred = calibrated_model.predict(X_train_scaled)
    test_pred = calibrated_model.predict(X_test_scaled)
    test_proba = calibrated_model.predict_proba(X_test_scaled)[:, 1]

    ood_detector = IsolationForest(
        n_estimators=200,
        contamination=0.03,
        random_state=42,
    )
    ood_detector.fit(X_train_scaled)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated_model, REALTIME_NATIVE_MODEL_PATH)
    joblib.dump(scaler, REALTIME_NATIVE_SCALER_PATH)
    joblib.dump(ood_detector, REALTIME_NATIVE_OOD_PATH)

    with open(REALTIME_NATIVE_FEATURE_LIST_PATH, "w", encoding="utf-8") as file:
        json.dump(REALTIME_NATIVE_FEATURES, file, indent=2)

    report = {
        "dataset_path": str(dataset_path),
        "feature_count": len(REALTIME_NATIVE_FEATURES),
        "training_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "performance": {
            "train_accuracy": float(accuracy_score(y_train, train_pred)),
            "test_accuracy": float(accuracy_score(y_test, test_pred)),
            "test_precision": float(precision_score(y_test, test_pred, zero_division=0)),
            "test_recall": float(recall_score(y_test, test_pred, zero_division=0)),
            "test_f1": float(f1_score(y_test, test_pred, zero_division=0)),
            "test_roc_auc": float(roc_auc_score(y_test, test_proba)),
        },
        "scientific_notes": {
            "training_mode": "bootstrap_proxy_until_realtime_history_available",
            "limitations": [
                "Humidity, BMKG alert, dan water level historis belum tersedia observasional penuh.",
                "Sebagian feature bootstrap masih diproksikan dari histori hujan Jakarta.",
            ],
            "strengths": [
                "Feature set kini 100% kompatibel dengan inference realtime.",
                "Temporal lag dan rolling rainfall menambah konteks dinamika banjir.",
                "Isolation Forest dipakai untuk OOD yang lebih robust.",
            ],
        },
    }

    model_card = {
        "model_name": "XGBoost Flood Predictor - Realtime Native",
        "purpose": "Realtime-native flood prediction using only operationally available signals",
        "feature_set": REALTIME_NATIVE_FEATURES,
        "training_dataset": str(dataset_path),
        "report_path": str(REALTIME_NATIVE_REPORT_PATH),
    }

    with open(REALTIME_NATIVE_MODEL_CARD_PATH, "w", encoding="utf-8") as file:
        json.dump(model_card, file, indent=2)
    with open(REALTIME_NATIVE_REPORT_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    return report

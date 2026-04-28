import json
from functools import lru_cache

import joblib
import numpy as np

from app.realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_file,
)
from app.utils.paths import DEFAULT_REALTIME_SNAPSHOT, MODELS_DIR, REPORTS_DIR


MODEL_PATH = MODELS_DIR / "flood_model_realtime_native.pkl"
SCALER_PATH = MODELS_DIR / "scaler_realtime_native.pkl"
OOD_PATH = MODELS_DIR / "ood_detector_realtime_native.pkl"
MODEL_CARD_PATH = MODELS_DIR / "model_card_realtime_native.json"


def _load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _classify(probability):
    if probability < 0.2:
        return "SAFE"
    if probability < 0.45:
        return "WARNING"
    return "DANGER"


def _risk_interpretation(risk_level, diagnostics):
    bmkg_source = diagnostics.get("bmkg_source", "no_alert")
    temporal_ready = diagnostics.get("temporal_features_ready", False)
    water_level_records = diagnostics.get("water_level_records", 0)

    if risk_level == "DANGER":
        if bmkg_source == "observed_alerts" and water_level_records > 0:
            return (
                "Risiko tinggi terdeteksi karena sinyal cuaca ekstrem sudah dikonfirmasi alert BMKG "
                "dan diperkuat oleh kondisi tinggi muka air. Ini menunjukkan potensi banjir yang "
                "bukan hanya prediksi statistik, tetapi juga konsisten dengan indikator lapangan."
            )
        return (
            "Risiko tinggi terdeteksi dari kombinasi hujan intens, akumulasi temporal, dan sinyal "
            "hidrologi. Kondisi ini mengindikasikan potensi genangan atau banjir meningkat dalam waktu dekat."
        )
    if risk_level == "WARNING":
        if temporal_ready:
            return (
                "Sistem melihat pola yang mulai mengarah ke banjir, terutama dari akumulasi hujan dan "
                "perubahan kondisi air. Belum berada pada level kritis, tetapi perlu pemantauan lebih rapat."
            )
        return (
            "Ada sinyal kewaspadaan awal dari cuaca dan hidrologi, tetapi bukti temporal belum sepenuhnya kuat. "
            "Status ini cocok untuk siaga operasional, bukan alarm penuh."
        )
    return (
        "Belum ada indikasi kuat banjir dari kombinasi cuaca, alert resmi, dan kondisi air saat ini. "
        "Monitoring tetap diperlukan karena situasi dapat berubah cepat di wilayah urban padat seperti Jakarta."
    )


def _recommended_action(risk_level):
    if risk_level == "DANGER":
        return [
            "Aktifkan koordinasi lintas pihak: BPBD/posko lokal, operator pintu air, dan tim lapangan di titik rawan.",
            "Keluarkan peringatan dini terarah untuk wilayah yang memiliki histori genangan atau elevasi rendah.",
            "Prioritaskan pemeriksaan pintu air, saluran utama, dan titik yang menunjukkan kenaikan muka air tercepat.",
        ]
    if risk_level == "WARNING":
        return [
            "Naikkan frekuensi monitoring BMKG, OpenWeather, dan Posko Banjir agar eskalasi bisa ditangkap lebih cepat.",
            "Siapkan personel siaga terbatas dan verifikasi kondisi drainase, pompa, atau titik limpasan yang sering bermasalah.",
            "Gunakan status ini untuk komunikasi internal dan kesiapan operasional, belum untuk alarm publik penuh.",
        ]
    return [
        "Lanjutkan monitoring rutin dan simpan histori realtime untuk retraining agar model makin akurat dari waktu ke waktu.",
        "Gunakan periode aman ini untuk validasi data, kalibrasi threshold, dan evaluasi kesiapan infrastruktur lokal.",
    ]


@lru_cache(maxsize=1)
def _load_assets() -> tuple:
    """Load and cache model assets on first call."""
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    ood_detector = joblib.load(OOD_PATH)
    model_card = _load_json(MODEL_CARD_PATH)
    return model, scaler, ood_detector, model_card


def predict_realtime_native(snapshot_path=DEFAULT_REALTIME_SNAPSHOT):
    model, scaler, ood_detector, model_card = _load_assets()

    engineered = build_realtime_native_features_from_file(snapshot_path=snapshot_path, persist_history=True)
    features = engineered.frame[REALTIME_NATIVE_FEATURES]
    scaled = scaler.transform(features)
    probability = float(model.predict_proba(scaled)[0, 1])
    ood_score = float(ood_detector.decision_function(scaled)[0])
    ood_label = int(ood_detector.predict(scaled)[0] == -1)
    risk_level = _classify(probability)

    result = {
        "model_variant": "realtime_native",
        "probability": probability,
        "risk_level": risk_level,
        "risk_interpretation": _risk_interpretation(risk_level, engineered.diagnostics),
        "recommended_action": _recommended_action(risk_level),
        "ood_detection": {
            "method": "IsolationForest",
            "score": ood_score,
            "is_outlier": bool(ood_label),
        },
        "features": features.iloc[0].to_dict(),
        "diagnostics": engineered.diagnostics,
        "model_name": model_card.get("model_name"),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "latest_realtime_native_prediction.json", "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    return json.loads(json.dumps(result, default=lambda value: float(value) if isinstance(value, np.generic) else value))

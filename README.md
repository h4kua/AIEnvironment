# Jakarta Flood Prediction System

Sistem prediksi banjir Jakarta yang menggabungkan:

- model historis berbasis XGBoost + SHAP
- model `realtime-native` berbasis sinyal operasional
- pipeline realtime dari Posko Banjir, BMKG Nowcast, dan OpenWeather
- API FastAPI untuk inference produksi

## Executive Summary

Project ini dirancang untuk kebutuhan kompetisi AI tingkat tinggi, dengan fokus pada:

- validitas ilmiah
- konsistensi antara training dan inference
- explainability dan Responsible AI
- kesiapan deployment realtime

Sistem menggunakan dua model:

1. `legacy_geospatial`
Model historis dengan feature geospasial yang kaya dan performa historis kuat.

2. `realtime_native`
Model ringan yang hanya memakai feature yang benar-benar tersedia saat inference realtime.

Pendekatan dual-model ini membantu narasi kompetisi:

- model lama menunjukkan kekuatan baseline dan kedalaman historis
- model baru menunjukkan kesesuaian operasional dan validitas deployment realtime

## Architecture

### 1. Data Ingestion

Pipeline `poskobanjir/` mengambil data dari:

- Posko Banjir DKI
- BMKG CAP / nowcast alerts
- OpenWeather API

Output utamanya:

- `poskobanjir/data/clean/realtime_snapshot.json`

### 2. Inference Layer

`app/services/` menangani:

- model loading
- realtime adapter
- prediction service
- report refresh
- data quality dan OOD monitoring

`app/realtime_native/` menangani:

- feature engineering realtime-native
- bootstrap dataset building
- training model baru
- inference realtime-native

### 3. API Layer

FastAPI tersedia di:

- `GET /health`
- `GET /predict/realtime`
- `GET /predict/realtime-native`

## Project Structure

```text
root/
├── app/
│   ├── api/
│   ├── services/
│   ├── realtime_native/
│   ├── agents/
│   └── utils/
├── poskobanjir/
├── artifacts/
│   ├── production/
│   ├── reports/
│   ├── visualizations/
│   ├── configurations/
│   └── legacy_archive/
├── models/
├── data/
│   ├── raw/
│   └── processed/
├── tests/
├── docs/
├── notebooks/
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Canonical Runtime Files

Model aktif:

- `models/flood_model_jakarta.pkl`
- `models/scaler_jakarta.pkl`
- `models/optimal_threshold.json`
- `models/feature_list_jakarta.json`
- `models/model_card_jakarta.json`

Model realtime-native:

- `models/feature_list_realtime_native.json`
- `models/model_card_realtime_native.json`
- artefak training/inference dikelola oleh `app/realtime_native/training.py`

Manifest produksi:

- `artifacts/production/catalog.json`

Laporan kompetisi:

- `artifacts/reports/advanced_model_report.txt`
- `artifacts/reports/project_summary.json`

## Quick Start

### 1. Install

```bash
python -m venv flood_env
flood_env\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Isi `.env` dengan:

- `OPENWEATHER_API_KEY`
- koordinat Jakarta bila diperlukan

### 3. Build Latest Snapshot

```bash
python poskobanjir/main.py
```

### 4. Run API

```bash
uvicorn app.api.main:app --reload
```

### 5. Call Endpoints

```bash
GET /predict/realtime
GET /predict/realtime-native
```

## Output Example

### Realtime Prediction

```json
{
  "probability": 0.41,
  "risk_level": "DANGER",
  "confidence_score": 0.78,
  "data_quality": {
    "score": 0.81
  },
  "model_warning": [],
  "explanation": [
    {
      "feature": "max_rainfall",
      "impact": "increase_risk"
    }
  ]
}
```

### Realtime-Native Prediction

```json
{
  "model_variant": "realtime_native",
  "probability": 0.47,
  "risk_level": "DANGER",
  "risk_interpretation": "Sinyal hujan, alert BMKG, atau kenaikan muka air menunjukkan risiko banjir aktif/meningkat.",
  "recommended_action": [
    "Aktifkan koordinasi posko dan validasi lapangan di titik rawan."
  ],
  "ood_detection": {
    "method": "IsolationForest",
    "is_outlier": false
  }
}
```

## Scientific Positioning

### Legacy Historical Model

Kelebihan:

- kaya feature historis dan geospasial
- performa baseline kuat

Keterbatasan:

- perlu adapter untuk feature yang tidak tersedia langsung saat realtime

### Realtime-Native Model

Kelebihan:

- feature training dan inference selaras
- lebih ringan
- lebih mudah dijelaskan ke reviewer non-teknis

Keterbatasan:

- histori observasional realtime penuh belum lengkap
- bootstrap dataset masih memakai proxy yang ditandai eksplisit

## Testing

```bash
pytest tests/unit/
```

## Important Notes For Reviewers

- File lama tidak dihapus langsung; semuanya dipindahkan ke `artifacts/legacy_archive/`
- Struktur runtime aktif dipertahankan bersih agar mudah diaudit
- `advanced_model_report.txt` dan `project_summary.json` tetap dipertahankan sebagai artefak kompetisi utama

## Useful References

- `docs/guides/REALTIME_NATIVE_MODEL_GUIDE.md`
- `docs/guides/API_USAGE_GUIDE.py`
- `artifacts/production/catalog.json`
- `artifacts/legacy_archive/README.md`

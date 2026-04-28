# Realtime-Native Flood Model

## Tujuan

Membangun model banjir yang hanya bergantung pada sinyal operasional yang memang tersedia pada saat inference realtime:

- curah hujan dari OpenWeather
- temperatur
- kelembapan
- alert BMKG CAP: severity, certainty, urgency
- rasio tinggi muka air dari Posko Banjir

## Feature Set Baru

Feature utama:

- `rainfall_mm`
- `rainfall_3h_proxy_mm`
- `rainfall_lag_1`
- `rainfall_lag_2`
- `rainfall_roll3_mean`
- `humidity_pct`
- `temperature_c`
- `bmkg_severity_score`
- `bmkg_certainty_score`
- `bmkg_urgency_score`
- `bmkg_weighted_score`
- `water_level_ratio`
- `water_level_lag_1`
- `water_level_delta`
- `hydro_meteorological_index`
- `monsoon_season`

## Dampak Feature Temporal

- `lag features` membantu model menangkap persistensi hujan dan keterlambatan respons banjir.
- `rolling rainfall average` membantu memodelkan akumulasi air, bukan hanya intensitas satu waktu.
- `water_level_delta` membantu mendeteksi percepatan kenaikan muka air.

## Validitas Ilmiah

Model ini lebih valid untuk deployment realtime karena feature saat training dan inference sejalan.

Keterbatasan saat ini:

- histori observasional BMKG/Posko/Humidity belum lengkap secara historis
- dataset training baru masih `bootstrap_proxy`

Artinya:

- model baru lebih kuat dari sisi *operational alignment*
- model lama masih lebih kuat dari sisi *historical richness*

## Perbandingan dengan Model Lama

### Model Lama

- kaya feature geospasial
- performa historis tinggi
- ada mismatch dengan inference realtime

### Model Realtime-Native

- lebih ringan dan deployable
- feature 100% operasional
- lebih mudah dijelaskan ke juri
- saat ini sebagian training feature masih berbasis proxy historis

## File Penting

- Training dataset bootstrap: `data/processed/realtime_native_training_bootstrap.csv`
- Sample dataset: `data/processed/realtime_native_training_sample.csv`
- Training code: `app/realtime_native/training.py`
- Inference code: `app/realtime_native/inference.py`
- Feature builder: `app/realtime_native/feature_builder.py`

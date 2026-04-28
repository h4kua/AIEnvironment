from app.realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_snapshot,
)


def test_build_realtime_native_features_from_snapshot_contains_temporal_columns():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.2, "humidity": 84},
            "rain": {"1h": 15.0, "3h": 36.0},
        },
        "bmkg_alerts": [
            {"severity": "Severe", "certainty": "Likely", "urgency": "Immediate"}
        ],
        "poskobanjir": [
            {
                "tinggi_air": "6400",
                "siaga1": "9500",
                "siaga2": "8500",
                "siaga3": "7500",
                "siaga4": "1",
            }
        ],
    }

    engineered = build_realtime_native_features_from_snapshot(snapshot, persist_history=False)

    assert list(engineered.frame.columns) == REALTIME_NATIVE_FEATURES
    assert engineered.frame.iloc[0]["rainfall_roll3_mean"] >= 0
    assert engineered.frame.iloc[0]["water_level_ratio"] >= 0
    assert engineered.frame.iloc[0]["bmkg_weighted_score"] > 0

from app.services.realtime_adapter import adapt_snapshot_to_features


def test_adapt_snapshot_to_features_builds_expected_feature_columns():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 30.5, "humidity": 82},
            "coord": {"lat": -6.2, "lon": 106.8},
            "rain": {"1h": 12.0},
        },
        "bmkg_alerts": [
            {
                "headline": "Hujan sedang hingga lebat",
                "severity": "Severe",
                "certainty": "Likely",
                "urgency": "Immediate",
            },
        ],
        "poskobanjir": [
            {
                "file_export": "Jakarta Selatan",
                "status": "Status : Siaga 3",
                "tinggi_air": "6400",
                "siaga1": "9500",
                "siaga2": "8500",
                "siaga3": "7500",
                "siaga4": "1",
            }
        ],
    }

    adapted = adapt_snapshot_to_features(snapshot)
    row = adapted.feature_frame.iloc[0]

    assert row["avg_rainfall"] >= 0
    assert row["max_rainfall"] >= row["avg_rainfall"]
    assert row["soil_moisture"] > 0
    assert row["extreme_weather"] in (0, 1)
    assert adapted.diagnostics["selected_region"] == "Jakarta Selatan"
    assert adapted.data_quality["score"] > 0
    assert adapted.diagnostics["bmkg_weighted_signal"]["normalized_score"] > 0


def test_adapt_snapshot_to_features_marks_citywide_baseline_when_region_missing():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.0, "humidity": 75},
            "coord": {"lat": -6.21, "lon": 106.84},
        },
        "bmkg_alerts": [],
        "poskobanjir": [],
    }

    adapted = adapt_snapshot_to_features(snapshot)

    assert adapted.diagnostics["selected_region"] == "DKI Jakarta"
    assert adapted.data_quality["feature_sources"]["elevation"] == "citywide_baseline"
    assert adapted.data_quality["score"] < 1.0

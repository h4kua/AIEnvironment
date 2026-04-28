"""
prepare_data.py — Jakarta Flood Event Dataset Processor (2013-2020)

WARNING: DATA LEAKAGE
---------------------
This dataset contains POST-EVENT information recorded AFTER floods occurred.
Fields such as ketinggian_air (water height), lama_genangan (inundation
duration), and casualty counts are OUTCOMES, not predictors.

    DO NOT USE AS MODEL INPUT FEATURES.

    VALID USES:
      - Evaluation benchmarking (did the model flag the right areas?)
      - Historical severity scoring for ActionAgent / EvaluationAgent
      - Validation ground-truth for competition scoring

Outputs:
  data/processed/events_clean.csv              - one row per event-day
  data/processed/event_summary_by_district.csv - aggregated by district x month
  data/processed/evaluation_scenarios.json     - structured evaluation records

Usage:
  python scripts/prepare_data.py
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
COMBINED_CSV = RAW_DIR / "combined.csv"

# ---------------------------------------------------------------------------
# District name normalization
# ---------------------------------------------------------------------------

DISTRICT_MAP: dict[str, str] = {
    "jakarta timur": "Jakarta Timur",
    "jakarta selatan": "Jakarta Selatan",
    "jakarta barat": "Jakarta Barat",
    "jakarta utara": "Jakarta Utara",
    "jakarta pusat": "Jakarta Pusat",
    "jakara barat": "Jakarta Barat",       # typo in source
    "jakarta urata": "Jakarta Utara",      # typo in source
    "kepulauan seribu": "Kepulauan Seribu",
}

BULAN_ID: dict[str, int] = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

# ---------------------------------------------------------------------------
# Severity weights (POST-EVENT only — NOT for ML model)
# WARNING: These columns are flood outcomes, forbidden as prediction features.
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, float] = {
    "water_max_cm": 0.35,
    "duration_days": 0.25,
    "jumlah_tempat_pengungsian": 0.25,
    "jumlah_meninggal": 0.15,
}

SEVERITY_CAPS: dict[str, float] = {
    "water_max_cm": 400.0,
    "duration_days": 14.0,
    "jumlah_tempat_pengungsian": 100.0,
    "jumlah_meninggal": 10.0,
}


# ---------------------------------------------------------------------------
# Column-swap fix for 2017 source data
#
# The 2017 source was concatenated with misaligned columns:
#   pandas 'ketinggian_air'    -> is actually tanggal_kejadian
#   pandas 'jumlah_luka_berat' -> is actually ketinggian_air
# ---------------------------------------------------------------------------

def _fix_2017_column_swap(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["tahun"] == 2017
    if not mask.any():
        return df
    df = df.copy()
    tmp_tanggal = df.loc[mask, "ketinggian_air"].copy()
    tmp_ketinggian = df.loc[mask, "jumlah_luka_berat"].copy()
    df.loc[mask, "tanggal_kejadian"] = tmp_tanggal
    df.loc[mask, "ketinggian_air"] = tmp_ketinggian
    df.loc[mask, "jumlah_luka_berat"] = "0"
    return df


# ---------------------------------------------------------------------------
# Field-level parsers
# ---------------------------------------------------------------------------

def normalize_district(val: object) -> str:
    if pd.isna(val):
        return "Unknown"
    s = str(val).strip().lower()
    return DISTRICT_MAP.get(s, str(val).strip().title())


def clean_location_field(val: object) -> str:
    """Remove KEC./KEL. prefixes and title-case."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    s = re.sub(r"^KEC\.\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^KEL\.\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^KEL\s+", "", s, flags=re.IGNORECASE)
    return s.strip().title()


def parse_water_height(val: object) -> dict[str, Optional[float]]:
    """
    POST-EVENT OUTCOME - NOT FOR ML MODEL INPUT.
    Parse ketinggian_air into min/max/mean centimetres.

    Handles: "20 - 250", "10 s/d 20 cm", "50 cm", "30", "800.0"
    """
    null: dict[str, Optional[float]] = {
        "water_min_cm": None,
        "water_max_cm": None,
        "water_mean_cm": None,
    }
    if pd.isna(val):
        return null

    s = str(val).strip().lower()
    if not s or s in ("0", "0.0", "nan"):
        return null

    s = re.sub(r"\s*cm\s*$", "", s).strip()
    s = re.sub(r"\s*s/d\s*", " - ", s, flags=re.IGNORECASE)

    range_m = re.match(r"^([\d.]+)\s*-\s*([\d.]+)$", s.strip())
    if range_m:
        lo, hi = float(range_m.group(1)), float(range_m.group(2))
        return {"water_min_cm": lo, "water_max_cm": hi, "water_mean_cm": (lo + hi) / 2.0}

    single_m = re.match(r"^([\d.]+)$", s.strip())
    if single_m:
        v = float(single_m.group(1))
        return {"water_min_cm": v, "water_max_cm": v, "water_mean_cm": v}

    return null


def parse_lama_genangan(val: object) -> float:
    """Parse flood inundation duration to float days."""
    if pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        pass

    s = str(val).strip().lower()
    range_m = re.search(r"([\d.]+)\s*(?:s/d|-)\s*([\d.]+)", s)
    if range_m:
        return (float(range_m.group(1)) + float(range_m.group(2))) / 2.0

    num_m = re.search(r"([\d.]+)", s)
    return float(num_m.group(1)) if num_m else 0.0


def parse_tanggal_kejadian(val: object, tahun: int, bulan: int) -> list[date]:
    """
    Parse messy tanggal_kejadian into a list of date objects.

    Handles all formats across 2013-2020:
      "9, 10, 11, 16 - 25"       2013-2016 numeric days
      "21 - 22\\n(2 Hari)"        2017 after column-swap fix
      "tgl. 21" / "tgl 27, "     2018-2019
      "tgl. 01 Januari"           2020 New-Year events
      "2020-12-07"                ISO dates in 2020
    """
    if pd.isna(val):
        return []

    s = str(val).strip()
    if not s or s in ("0", "0.0", "nan"):
        return []

    # ISO date: 2020-12-07
    iso_m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if iso_m:
        try:
            return [date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))]
        except ValueError:
            return []

    # Strip "tgl." / "tgl " prefix
    s = re.sub(r"^tgl\.?\s*", "", s, flags=re.IGNORECASE).strip()

    # Extract Indonesian month name and override bulan
    for month_name, month_num in BULAN_ID.items():
        if month_name in s.lower():
            bulan = month_num
            s = re.sub(month_name, "", s, flags=re.IGNORECASE).strip()
            break

    # Strip "(X Hari)" duration annotations and normalize newlines
    s = re.sub(r"\(\d+\s*[Hh]ari\)", "", s)
    s = s.replace("\n", ",")
    s = s.strip(" ,")

    days: list[int] = []
    for part in (p.strip() for p in s.split(",") if p.strip()):
        rng = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if rng:
            days.extend(range(int(rng.group(1)), int(rng.group(2)) + 1))
        elif re.match(r"^\d+$", part):
            days.append(int(part))

    results: list[date] = []
    for d in days:
        try:
            results.append(date(tahun, bulan, d))
        except ValueError:
            pass  # skip invalid calendar days e.g. Feb 30
    return results


# ---------------------------------------------------------------------------
# Severity scoring (POST-EVENT only)
# ---------------------------------------------------------------------------

def _compute_severity(df: pd.DataFrame) -> pd.Series:
    """
    POST-EVENT DATA - NOT FOR ML MODEL INPUT.
    Weighted 0-1 composite for ActionAgent / EvaluationAgent use ONLY.
    """
    score = pd.Series(0.0, index=df.index)
    for col, cap in SEVERITY_CAPS.items():
        series = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(0.0)
        score += (series / cap).clip(0.0, 1.0) * SEVERITY_WEIGHTS[col]
    return score.round(4)


# ---------------------------------------------------------------------------
# Cleaning pipeline
# ---------------------------------------------------------------------------

def clean_combined(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["tahun"] = pd.to_numeric(df["tahun"], errors="coerce")
    df["bulan"] = pd.to_numeric(df["bulan"], errors="coerce")
    df = df.dropna(subset=["tahun", "bulan"])
    df["tahun"] = df["tahun"].astype(int)
    df["bulan"] = df["bulan"].astype(int)

    df = _fix_2017_column_swap(df)

    df["kota_administrasi"] = df["kota_administrasi"].apply(normalize_district)
    df["kecamatan"] = df["kecamatan"].apply(clean_location_field)
    df["kelurahan"] = df["kelurahan"].apply(clean_location_field)

    water_parsed = df["ketinggian_air"].apply(parse_water_height)
    df["water_min_cm"] = water_parsed.apply(lambda x: x["water_min_cm"])
    df["water_max_cm"] = water_parsed.apply(lambda x: x["water_max_cm"])
    df["water_mean_cm"] = water_parsed.apply(lambda x: x["water_mean_cm"])

    df["duration_days"] = df["lama_genangan"].apply(parse_lama_genangan)

    for col in ["jumlah_tempat_pengungsian", "jumlah_luka_ringan",
                "jumlah_luka_berat", "jumlah_meninggal"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["event_dates"] = df.apply(
        lambda r: parse_tanggal_kejadian(r["tanggal_kejadian"], r["tahun"], r["bulan"]),
        axis=1,
    )

    df["flood_event"] = 1
    df["severity"] = _compute_severity(df)

    return df


# ---------------------------------------------------------------------------
# Daily expansion
# ---------------------------------------------------------------------------

def expand_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Expand each source row to one row per event-day."""
    records: list[dict] = []
    for row in df.to_dict("records"):
        dates: list[date] = row.pop("event_dates", [])
        if not dates:
            try:
                dates = [date(row["tahun"], row["bulan"], 1)]
            except (ValueError, KeyError):
                continue
        for d in dates:
            records.append({**row, "event_date": pd.Timestamp(d)})
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_by_district(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate flood events to district x year-month summary."""
    work = df.copy()
    work["year_month"] = work["event_date"].dt.to_period("M").astype(str)

    agg = (
        work.groupby(["kota_administrasi", "year_month"])
        .agg(
            event_count=("flood_event", "sum"),
            avg_severity=("severity", "mean"),
            max_water_cm=("water_max_cm", "max"),
            total_evacuees=("jumlah_tempat_pengungsian", "sum"),
            total_fatalities=("jumlah_meninggal", "sum"),
            kelurahan_count=("kelurahan", "nunique"),
        )
        .reset_index()
    )
    agg["avg_severity"] = agg["avg_severity"].round(4)
    agg["max_water_cm"] = agg["max_water_cm"].round(1)
    return agg.sort_values(["year_month", "kota_administrasi"])


# ---------------------------------------------------------------------------
# Evaluation scenarios
# ---------------------------------------------------------------------------

def build_evaluation_scenarios(df: pd.DataFrame) -> list[dict]:
    """
    Build structured evaluation records for EvaluationAgent benchmarking.

    Each record is one confirmed flood event-day at a specific location.
    The leakage_warning field is a mandatory guardrail — callers must not
    pass severity, water_max_cm, or duration_days as model input features.
    """
    scenarios: list[dict] = []
    for row in df.to_dict("records"):
        ed = row.get("event_date")
        scenarios.append({
            "date": pd.Timestamp(ed).strftime("%Y-%m-%d") if pd.notna(ed) else None,
            "district": row.get("kota_administrasi"),
            "kecamatan": row.get("kecamatan"),
            "kelurahan": row.get("kelurahan"),
            "event": True,
            "flood_event": 1,
            "severity": float(row.get("severity") or 0.0),
            "water_max_cm": (
                float(row["water_max_cm"])
                if pd.notna(row.get("water_max_cm"))
                else None
            ),
            "duration_days": float(row.get("duration_days") or 0.0),
            "evacuees": int(row.get("jumlah_tempat_pengungsian") or 0),
            "fatalities": int(row.get("jumlah_meninggal") or 0),
            "data_source": "post_event",
            "leakage_warning": (
                "POST-EVENT DATA - DO NOT USE AS PREDICTION INPUT. "
                "severity/water_max_cm/duration_days are OUTCOMES, not features."
            ),
        })
    return scenarios


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading %s ...", COMBINED_CSV)
    df_raw = pd.read_csv(COMBINED_CSV, dtype=str)
    logger.info("Loaded %d rows", len(df_raw))

    logger.info("Cleaning ...")
    df_clean = clean_combined(df_raw)

    logger.info("Expanding to daily event rows ...")
    df_daily = expand_to_daily(df_clean)
    logger.info("Expanded to %d event-day rows", len(df_daily))

    # events_clean.csv
    keep_cols = [
        "event_date", "kota_administrasi", "kecamatan", "kelurahan",
        "tahun", "bulan", "flood_event", "duration_days",
        "water_min_cm", "water_max_cm", "water_mean_cm",
        "jumlah_tempat_pengungsian", "jumlah_luka_ringan",
        "jumlah_luka_berat", "jumlah_meninggal",
        "severity",
    ]
    present = [c for c in keep_cols if c in df_daily.columns]
    out_events = OUT_DIR / "events_clean.csv"
    df_daily[present].to_csv(out_events, index=False)
    logger.info("Saved %s (%d rows)", out_events, len(df_daily))

    # event_summary_by_district.csv
    df_summary = aggregate_by_district(df_daily)
    out_summary = OUT_DIR / "event_summary_by_district.csv"
    df_summary.to_csv(out_summary, index=False)
    logger.info("Saved %s (%d rows)", out_summary, len(df_summary))

    # evaluation_scenarios.json
    scenarios = build_evaluation_scenarios(df_daily)
    out_json = OUT_DIR / "evaluation_scenarios.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(scenarios, fh, ensure_ascii=False, indent=2)
    logger.info("Saved %s (%d scenarios)", out_json, len(scenarios))

    logger.info("Done.")


if __name__ == "__main__":
    main()

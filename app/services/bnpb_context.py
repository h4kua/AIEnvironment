"""
BNPB InaRISK vulnerability context service for DKI Jakarta.

Fetches long-term regional flood vulnerability from BNPB InaRISK and maps
location strings to Jakarta kota with deterministic confidence scoring.

CRITICAL CONTRACT:
  - This data MUST NOT influence ML probability or risk_level
  - Only affects: manual_review threshold, action priority, routing preference
  - Mapping confidence < 0.70 → BNPB data is silently ignored
  - Data vintage > 365 days → BNPB data is silently ignored
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ─── Confidence threshold ─────────────────────────────────────────────────────
# Below this, district mapping is too ambiguous to use BNPB data safely.
MAPPING_CONFIDENCE_THRESHOLD = 0.70

# ─── Jakarta kota BPS codes ───────────────────────────────────────────────────
_JAKARTA_KOTA_CODES: frozenset[str] = frozenset({"3171", "3172", "3173", "3174", "3175"})

_CODE_TO_KOTA: dict[str, str] = {
    "3171": "Jakarta Selatan",
    "3172": "Jakarta Timur",
    "3173": "Jakarta Pusat",
    "3174": "Jakarta Barat",
    "3175": "Jakarta Utara",
}

# ─── Deterministic alias dictionary ──────────────────────────────────────────
# Maps exact lowercase strings → canonical kota name.
# Covers: official kota names, abbreviations, English translations,
# all 44 kecamatan, and commonly referenced kelurahan / landmarks.
# NO generic "jakarta" fallback — ambiguous inputs are rejected, not guessed.
_EXACT_ALIASES: dict[str, str] = {
    # ── Jakarta Pusat (Kota code 3173) ───────────────────────────────────────
    "jakarta pusat":        "Jakarta Pusat",
    "jak-pus":              "Jakarta Pusat",
    "jakpus":               "Jakarta Pusat",
    "central jakarta":      "Jakarta Pusat",
    "kota jakarta pusat":   "Jakarta Pusat",
    "kab. jakarta pusat":   "Jakarta Pusat",
    # Kecamatan (8)
    "gambir":               "Jakarta Pusat",
    "sawah besar":          "Jakarta Pusat",
    "kemayoran":            "Jakarta Pusat",
    "senen":                "Jakarta Pusat",
    "cempaka putih":        "Jakarta Pusat",
    "menteng":              "Jakarta Pusat",
    "tanah abang":          "Jakarta Pusat",
    "johar baru":           "Jakarta Pusat",
    # Notable kelurahan / landmarks
    "senayan":              "Jakarta Pusat",
    "monas":                "Jakarta Pusat",
    "petamburan":           "Jakarta Pusat",
    "benhil":               "Jakarta Pusat",
    "bendungan hilir":      "Jakarta Pusat",
    "cideng":               "Jakarta Pusat",
    "mangga dua":           "Jakarta Pusat",

    # ── Jakarta Utara (Kota code 3175) ───────────────────────────────────────
    "jakarta utara":        "Jakarta Utara",
    "jak-ut":               "Jakarta Utara",
    "jakut":                "Jakarta Utara",
    "north jakarta":        "Jakarta Utara",
    "kota jakarta utara":   "Jakarta Utara",
    "kab. jakarta utara":   "Jakarta Utara",
    # Kecamatan (6)
    "penjaringan":          "Jakarta Utara",
    "pademangan":           "Jakarta Utara",
    "tanjung priok":        "Jakarta Utara",
    "koja":                 "Jakarta Utara",
    "kelapa gading":        "Jakarta Utara",
    "cilincing":            "Jakarta Utara",
    # Notable kelurahan / landmarks
    "pluit":                "Jakarta Utara",
    "muara baru":           "Jakarta Utara",
    "ancol":                "Jakarta Utara",
    "sunter":               "Jakarta Utara",
    "priok":                "Jakarta Utara",
    "warakas":              "Jakarta Utara",
    "pegangsaan dua":       "Jakarta Utara",
    "tanjung priok port":   "Jakarta Utara",
    "pelabuhan":            "Jakarta Utara",

    # ── Jakarta Barat (Kota code 3174) ───────────────────────────────────────
    "jakarta barat":        "Jakarta Barat",
    "jak-bar":              "Jakarta Barat",
    "jakbar":               "Jakarta Barat",
    "west jakarta":         "Jakarta Barat",
    "kota jakarta barat":   "Jakarta Barat",
    "kab. jakarta barat":   "Jakarta Barat",
    # Kecamatan (8)
    "cengkareng":           "Jakarta Barat",
    "kalideres":            "Jakarta Barat",
    "kebon jeruk":          "Jakarta Barat",
    "kembangan":            "Jakarta Barat",
    "grogol petamburan":    "Jakarta Barat",
    "taman sari":           "Jakarta Barat",
    "tambora":              "Jakarta Barat",
    "palmerah":             "Jakarta Barat",
    # Notable kelurahan / landmarks
    "kapuk":                "Jakarta Barat",
    "kamal":                "Jakarta Barat",
    "grogol":               "Jakarta Barat",
    "slipi":                "Jakarta Barat",
    "glodok":               "Jakarta Barat",
    "kota tua":             "Jakarta Barat",
    "mangga besar":         "Jakarta Barat",
    "jembatan lima":        "Jakarta Barat",
    "duri kepa":            "Jakarta Barat",
    "kali deres":           "Jakarta Barat",
    "rawa buaya":           "Jakarta Barat",

    # ── Jakarta Timur (Kota code 3172) ───────────────────────────────────────
    "jakarta timur":        "Jakarta Timur",
    "jak-tim":              "Jakarta Timur",
    "jaktim":               "Jakarta Timur",
    "east jakarta":         "Jakarta Timur",
    "kota jakarta timur":   "Jakarta Timur",
    "kab. jakarta timur":   "Jakarta Timur",
    # Kecamatan (10)
    "matraman":             "Jakarta Timur",
    "pulo gadung":          "Jakarta Timur",
    "jatinegara":           "Jakarta Timur",
    "duren sawit":          "Jakarta Timur",
    "kramat jati":          "Jakarta Timur",
    "cakung":               "Jakarta Timur",
    "pasar rebo":           "Jakarta Timur",
    "ciracas":              "Jakarta Timur",
    "cipayung":             "Jakarta Timur",
    "makassar":             "Jakarta Timur",
    "makasar":              "Jakarta Timur",
    # Notable kelurahan / landmarks
    "kampung melayu":       "Jakarta Timur",
    "cawang":               "Jakarta Timur",
    "klender":              "Jakarta Timur",
    "rawa bunga":           "Jakarta Timur",
    "bidara cina":          "Jakarta Timur",
    "pondok bambu":         "Jakarta Timur",
    "buaran":               "Jakarta Timur",
    "pulo gadung":          "Jakarta Timur",
    "pisangan":             "Jakarta Timur",

    # ── Jakarta Selatan (Kota code 3171) ─────────────────────────────────────
    "jakarta selatan":      "Jakarta Selatan",
    "jak-sel":              "Jakarta Selatan",
    "jaksel":               "Jakarta Selatan",
    "south jakarta":        "Jakarta Selatan",
    "kota jakarta selatan": "Jakarta Selatan",
    "kab. jakarta selatan": "Jakarta Selatan",
    # Kecamatan (10)
    "tebet":                "Jakarta Selatan",
    "setiabudi":            "Jakarta Selatan",
    "mampang prapatan":     "Jakarta Selatan",
    "pasar minggu":         "Jakarta Selatan",
    "cilandak":             "Jakarta Selatan",
    "kebayoran baru":       "Jakarta Selatan",
    "kebayoran lama":       "Jakarta Selatan",
    "pesanggrahan":         "Jakarta Selatan",
    "jagakarsa":            "Jakarta Selatan",
    "pancoran":             "Jakarta Selatan",
    # Notable kelurahan / landmarks
    "manggarai":            "Jakarta Selatan",
    "bukit duri":           "Jakarta Selatan",
    "rawajati":             "Jakarta Selatan",
    "kalibata":             "Jakarta Selatan",
    "blok m":               "Jakarta Selatan",
    "kebayoran":            "Jakarta Selatan",
    "pondok indah":         "Jakarta Selatan",
    "fatmawati":            "Jakarta Selatan",
    "cipete":               "Jakarta Selatan",
    "kemang":               "Jakarta Selatan",
    "kuningan":             "Jakarta Selatan",
    "rasuna said":          "Jakarta Selatan",
    "casablanca":           "Jakarta Selatan",
    "gatot subroto":        "Jakarta Selatan",
}

# Canonical lowercase → canonical proper-case (for substring containment check)
_CANONICAL_LOWER: dict[str, str] = {
    "jakarta pusat":   "Jakarta Pusat",
    "jakarta utara":   "Jakarta Utara",
    "jakarta barat":   "Jakarta Barat",
    "jakarta timur":   "Jakarta Timur",
    "jakarta selatan": "Jakarta Selatan",
}

# Short kota aliases used in the exact alias check to distinguish kota-level
# matches (confidence 0.95) from kecamatan/kelurahan matches (confidence 0.90)
_KOTA_LEVEL_TOKENS: frozenset[str] = frozenset({
    "jak-pus", "jakpus", "jak-ut", "jakut", "jak-bar", "jakbar",
    "jak-tim", "jaktim", "jak-sel", "jaksel",
    "central jakarta", "north jakarta", "west jakarta",
    "east jakarta", "south jakarta",
    "kota jakarta pusat", "kota jakarta utara", "kota jakarta barat",
    "kota jakarta timur", "kota jakarta selatan",
    "jakarta pusat", "jakarta utara", "jakarta barat",
    "jakarta timur", "jakarta selatan",
    "kab. jakarta pusat", "kab. jakarta utara", "kab. jakarta barat",
    "kab. jakarta timur", "kab. jakarta selatan",
})

# ─── Score normalisation & classification ────────────────────────────────────
_IRBI_NORMALISE_MAX = 300.0
_THRESHOLD_VERY_HIGH = 0.75
_THRESHOLD_HIGH = 0.55
_THRESHOLD_MEDIUM = 0.35
_MAX_VINTAGE_DAYS = 365
_CACHE_TTL = 86_400

# ─── API endpoints ────────────────────────────────────────────────────────────
_URL_IRBI     = "https://inarisk.bnpb.go.id/api/bencana-irbi"
_URL_PASOET   = "https://inarisk.bnpb.go.id/api/data_pasoet"
_URL_PROVINSI = "https://inarisk.bnpb.go.id/api/provinsi"
_TIMEOUT      = 10.0

_cache: dict = {}


# ─── Public dataclass ─────────────────────────────────────────────────────────

@dataclass
class VulnerabilityContext:
    """
    Long-term regional flood vulnerability for a Jakarta kota.

    irbi_flood_score:     Raw normalised IRBI flood sub-index (0.0–1.0).
    effective_irbi_score: Decay-adjusted score. THIS is what consuming agents use.
                          Decays toward 50% of raw score over 730 days.
    exposure_class:       Classified from effective_irbi_score.
    """

    irbi_flood_score: float       # Raw normalised IRBI, 0.0–1.0
    effective_irbi_score: float   # Staleness-decayed (used by all agents)
    exposure_class: str           # LOW | MEDIUM | HIGH | VERY_HIGH
    affected_population: int
    data_vintage_days: int
    district: str

    def to_dict(self) -> dict:
        return {
            "irbi_score": round(self.irbi_flood_score, 4),
            "effective_irbi_score": round(self.effective_irbi_score, 4),
            "exposure_class": self.exposure_class,
            "population": self.affected_population,
            "district": self.district,
            "data_vintage_days": self.data_vintage_days,
        }


# ─── Public mapping function ─────────────────────────────────────────────────

def map_to_jakarta_district(location_str: str) -> tuple[str | None, float]:
    """
    Deterministically map a location string to one of five canonical Jakarta kota names.

    Confidence tiers:
      1.00 — exact canonical kota name (e.g. "Jakarta Timur")
      0.95 — exact kota-level alias (abbreviation, English name)
      0.90 — exact kecamatan or kelurahan name
      0.80 — canonical kota name found as substring of input
      0.75 — kecamatan/kelurahan alias found as substring of input
      0.00 — no match

    Returns (None, 0.0) for any input that cannot be confidently matched.
    NO silent fallback to "Jakarta Pusat" or any other default.
    Callers must check confidence >= MAPPING_CONFIDENCE_THRESHOLD before using.
    """
    if not location_str:
        return None, 0.0

    n = location_str.lower().strip()
    if not n:
        return None, 0.0

    # Tier 1: exact canonical name
    if n in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[n], 1.0

    # Tier 2 & 3: exact alias lookup (kota-level vs kecamatan-level)
    if n in _EXACT_ALIASES:
        district = _EXACT_ALIASES[n]
        confidence = 0.95 if n in _KOTA_LEVEL_TOKENS else 0.90
        return district, confidence

    # Tier 4: canonical kota name contained in the input string
    for canon_lower, canon in _CANONICAL_LOWER.items():
        if canon_lower in n:
            return canon, 0.80

    # Tier 5: kecamatan/kelurahan alias contained in input (minimum length guard)
    # Sort by alias length descending so more specific matches win
    for alias, district in sorted(_EXACT_ALIASES.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 6 and alias in n:
            return district, 0.75

    return None, 0.0


# ─── Public context accessor ─────────────────────────────────────────────────

def get_vulnerability_context(
    location_str: str,
) -> tuple[Optional[VulnerabilityContext], dict]:
    """
    Return (VulnerabilityContext | None, mapping_info).

    mapping_info is ALWAYS returned so the caller can emit it in output JSON
    regardless of whether vulnerability data is available.

    Returns (None, mapping_info) when:
      - mapping confidence < MAPPING_CONFIDENCE_THRESHOLD
      - BNPB data unavailable (API down, never fetched)
      - Data vintage > _MAX_VINTAGE_DAYS
      - Any unexpected error

    Never raises.
    """
    district, confidence = map_to_jakarta_district(location_str)
    mapping_info: dict = {
        "input_location": location_str,
        "mapped_district": district if confidence >= MAPPING_CONFIDENCE_THRESHOLD else None,
        "confidence": round(confidence, 4),
    }

    if not district or confidence < MAPPING_CONFIDENCE_THRESHOLD:
        return None, mapping_info

    try:
        raw_data = fetch_bnpb_data()
        raw_ctx = raw_data.get(district)
        if not raw_ctx:
            return None, mapping_info
        if raw_ctx.data_vintage_days > _MAX_VINTAGE_DAYS:
            logger.debug(
                "BNPB data for %s is %d days old (> %d) — suppressed.",
                district, raw_ctx.data_vintage_days, _MAX_VINTAGE_DAYS,
            )
            return None, mapping_info

        # Build context with decay-adjusted effective score
        effective = _apply_staleness_decay(raw_ctx.irbi_flood_score, raw_ctx.data_vintage_days)
        ctx = VulnerabilityContext(
            irbi_flood_score=raw_ctx.irbi_flood_score,
            effective_irbi_score=effective,
            exposure_class=_classify_exposure(effective),
            affected_population=raw_ctx.affected_population,
            data_vintage_days=raw_ctx.data_vintage_days,
            district=district,
        )
        return ctx, mapping_info

    except Exception as exc:  # noqa: BLE001
        logger.debug("get_vulnerability_context(%r) suppressed: %s", location_str, exc)
        return None, mapping_info


# ─── Cache & fetch ────────────────────────────────────────────────────────────

def fetch_bnpb_data() -> dict[str, VulnerabilityContext]:
    """
    Return the current cached BNPB vulnerability map for DKI Jakarta kota.
    Refreshed every 24 hours. Falls back to last good cache on failure.
    Never raises.
    """
    global _cache

    age = time.monotonic() - _cache.get("fetched_at", 0.0)
    if _cache and age < _CACHE_TTL:
        return _cache["data"]

    try:
        fresh = _fetch_from_apis()
        _cache = {"fetched_at": time.monotonic(), "data": fresh}
        logger.info("BNPB InaRISK refreshed — %d Jakarta kota loaded.", len(fresh))
        return fresh
    except Exception as exc:  # noqa: BLE001
        fallback = "cached data" if _cache.get("data") else "empty (no prior fetch)"
        logger.warning("BNPB API fetch failed (%s) — using %s.", exc, fallback)
        return _cache.get("data", {})


def _fetch_from_apis() -> dict[str, VulnerabilityContext]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        irbi_raw   = _safe_get(client, _URL_IRBI)
        pasoet_raw = _safe_get(client, _URL_PASOET)
        _safe_get(client, _URL_PROVINSI)  # verifies DKI Jakarta present

    irbi_scores  = _parse_irbi(irbi_raw)
    pop_counts   = _parse_pasoet(pasoet_raw)
    vintage_days = _estimate_vintage_days(irbi_raw)

    result: dict[str, VulnerabilityContext] = {}
    for kota, raw_score in irbi_scores.items():
        normalised = min(1.0, max(0.0, raw_score / _IRBI_NORMALISE_MAX))
        # Store raw normalised score; effective_irbi_score is computed at read time
        # (in get_vulnerability_context) after vintage is known.
        result[kota] = VulnerabilityContext(
            irbi_flood_score=round(normalised, 4),
            effective_irbi_score=round(normalised, 4),  # overwritten on read
            exposure_class=_classify_exposure(normalised),
            affected_population=pop_counts.get(kota, 0),
            data_vintage_days=vintage_days,
            district=kota,
        )
    return result


def _safe_get(client: httpx.Client, url: str) -> dict | list:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


# ─── Parse helpers ────────────────────────────────────────────────────────────

def _parse_irbi(raw: dict | list) -> dict[str, float]:
    """Extract flood IRBI scores for Jakarta kota from bencana-irbi response."""
    records: list = raw if isinstance(raw, list) else raw.get("data", [])

    flood_scores: dict[str, float] = {}
    composite_scores: dict[str, float] = {}

    for rec in records:
        kode    = str(rec.get("kode_kab") or rec.get("kodeKab") or "")
        nama    = str(rec.get("nama_kab") or rec.get("namaKab") or rec.get("nama") or "")
        bencana = str(rec.get("bencana") or rec.get("jenis_bencana") or "").lower()
        score   = _coerce_float(
            rec.get("irbi") or rec.get("skor_irbi") or rec.get("score") or rec.get("nilai")
        )
        if score is None:
            continue
        if kode not in _JAKARTA_KOTA_CODES and "jakarta" not in nama.lower():
            continue

        canonical = _CODE_TO_KOTA.get(kode) or _resolve_kota_from_name(nama)
        if not canonical:
            continue

        if "banjir" in bencana or "flood" in bencana:
            flood_scores[canonical] = max(flood_scores.get(canonical, 0.0), score)
        else:
            composite_scores[canonical] = max(composite_scores.get(canonical, 0.0), score)

    return flood_scores if flood_scores else composite_scores


def _parse_pasoet(raw: dict | list) -> dict[str, int]:
    """Extract exposed population counts for Jakarta kota from data_pasoet."""
    records: list = raw if isinstance(raw, list) else raw.get("data", [])
    result: dict[str, int] = {}

    for rec in records:
        kode = str(rec.get("kode_kab") or rec.get("kodeKab") or "")
        nama = str(rec.get("nama_kab") or rec.get("namaKab") or rec.get("nama") or "")
        pop  = _coerce_int(
            rec.get("penduduk_terpapar") or rec.get("populasi_terpapar")
            or rec.get("total_penduduk") or rec.get("jumlah_penduduk")
            or rec.get("population")
        )
        if kode not in _JAKARTA_KOTA_CODES and "jakarta" not in nama.lower():
            continue
        canonical = _CODE_TO_KOTA.get(kode) or _resolve_kota_from_name(nama)
        if canonical and pop is not None:
            result[canonical] = max(result.get(canonical, 0), pop)

    return result


def _resolve_kota_from_name(name: str) -> str | None:
    """Resolve kota name from BNPB's raw nama_kab field using the canonical map."""
    n = name.lower().strip()
    if n in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[n]
    for canon_lower, canon in _CANONICAL_LOWER.items():
        if canon_lower in n:
            return canon
    return None


def _estimate_vintage_days(raw: dict | list) -> int:
    records: list = raw if isinstance(raw, list) else raw.get("data", [])
    first = records[0] if records else {}

    for field in ("last_updated", "updated_at", "tanggal_update", "tgl_update", "tanggal"):
        val = first.get(field)
        if val:
            try:
                dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                return max(0, (datetime.now(timezone.utc) - dt).days)
            except (ValueError, TypeError):
                pass

    tahun = first.get("tahun") or first.get("year")
    if tahun:
        try:
            mid_year = datetime(int(tahun), 7, 1, tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - mid_year).days)
        except (ValueError, TypeError):
            pass

    return 365


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _apply_staleness_decay(irbi_score: float, vintage_days: int) -> float:
    """
    Time-based decay on IRBI score. Decays toward 50% floor over 730 days.

    Formula: effective = irbi_score * max(0.5, 1 - vintage_days / 730)

    At   0 days: factor = 1.00 (no decay)
    At 180 days: factor = 0.75
    At 365 days: factor = 0.50 (floor)
    """
    decay_factor = max(0.5, 1.0 - vintage_days / 730.0)
    return round(irbi_score * decay_factor, 4)


def _classify_exposure(score: float) -> str:
    if score > _THRESHOLD_VERY_HIGH:
        return "VERY_HIGH"
    if score > _THRESHOLD_HIGH:
        return "HIGH"
    if score > _THRESHOLD_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _coerce_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _coerce_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

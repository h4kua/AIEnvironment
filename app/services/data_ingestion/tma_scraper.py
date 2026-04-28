"""
TMA (Tinggi Muka Air) scraper — Jakarta flood-gate water-level ingestion.

Fetches real-time water-height readings from the BPBD Jakarta scraping proxy.
Data is classified as LOW reliability (scraping proxy, not a certified API)
and this is explicitly surfaced in every response so downstream agents can
weight it appropriately in confidence calculations.

Failure modes handled:
  - Network timeout or connection error  → retry up to _MAX_RETRIES, then DEGRADED
  - HTTP non-200 status                  → retry, then DEGRADED
  - Invalid / non-JSON response body     → DEGRADED
  - Missing required fields              → INVALID
  - time/ketinggian length mismatch      → INVALID
  - Empty data after parsing             → DEGRADED
  - All retries exhausted                → DEGRADED with last-valid cache fallback
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone
from typing import Any

import requests

# ─── Configuration ────────────────────────────────────────────────────────────

_PROXY_URL = (
    "https://web.animemusic.us/api-track-aksesibilitas/index.php"
    "?web=bpbd.jakarta.go.id&menu-disabilitas=no_data"
)
_TIMEOUT_SECONDS = 8
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 2

# ─── Module-level last-valid cache ───────────────────────────────────────────
# Stores the last successfully parsed response so the system degrades to it
# when the upstream proxy is temporarily unavailable.
_last_valid_cache: dict | None = None


# ─── Internal helpers ────────────────────────────────────────────────────────

def _split_csv(value: Any) -> list[str]:
    """Accept a comma-separated string or a list; return cleaned string tokens."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _parse_records(raw: dict) -> tuple[list[dict], str | None]:
    """
    Convert raw JSON into structured records.

    Returns (records, warning_note). warning_note is None on clean success.
    """
    times = _split_csv(raw.get("time"))
    heights = _split_csv(raw.get("ketinggian"))

    if not times and not heights:
        return [], "Both 'time' and 'ketinggian' fields are absent or empty."
    if not times:
        return [], "Field 'time' is absent or empty."
    if not heights:
        return [], "Field 'ketinggian' is absent or empty."
    if len(times) != len(heights):
        return [], (
            f"Length mismatch: {len(times)} time entries vs {len(heights)} ketinggian entries."
        )

    records: list[dict] = []
    skipped = 0
    for t, h in zip(times, heights):
        try:
            records.append({"time": t, "height_cm": float(h)})
        except (ValueError, TypeError):
            skipped += 1

    if not records:
        return [], f"All {len(times)} ketinggian values failed numeric conversion."

    note = f"{skipped} record(s) skipped (non-numeric ketinggian)." if skipped else None
    return records, note


def _build_response(
    status: str,
    reason: str | None,
    source: str,
    data: list[dict],
) -> dict:
    return {
        "status": status,
        "reason": reason,
        "source": source,
        # Scraping-proxy data is always low reliability — operators must know this.
        "reliability": "low",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def _fallback_response(reason: str) -> dict:
    """Return cached data when all fetch attempts fail."""
    if _last_valid_cache:
        return {
            **_last_valid_cache,
            "status": "DEGRADED",
            "source": "cache",
            "reason": reason + " — serving last valid cached data.",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    return _build_response(
        status="DEGRADED",
        reason=reason + " — no cached data available.",
        source="scraping_proxy",
        data=[],
    )


# ─── Public API ──────────────────────────────────────────────────────────────

def fetch_tma_data() -> dict:
    """
    Fetch current water-level readings from the BPBD Jakarta scraping proxy.

    Always returns a valid dict — never raises. On partial or complete failure
    the caller receives status='DEGRADED' or 'INVALID' with an explanatory reason.

    Return schema:
    {
        "status":      "OK" | "INVALID" | "DEGRADED",
        "reason":      str | None,       # None on clean OK
        "source":      "scraping_proxy" | "cache",
        "reliability": "low",            # always low for this source
        "fetched_at":  "<ISO-8601 UTC>",
        "data": [
            {"time": "HH:MM", "height_cm": 120.0},
            ...
        ]
    }
    """
    global _last_valid_cache

    last_error: str = "Unknown error"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(
                _PROXY_URL,
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": "JakartaFloodSystem/1.0"},
            )

            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                if attempt < _MAX_RETRIES:
                    _time.sleep(_RETRY_DELAY_SECONDS)
                continue

            try:
                raw = resp.json()
            except ValueError:
                last_error = "Response body is not valid JSON"
                if attempt < _MAX_RETRIES:
                    _time.sleep(_RETRY_DELAY_SECONDS)
                continue

            if not isinstance(raw, dict):
                return _build_response(
                    status="INVALID",
                    reason=f"Expected JSON object, got {type(raw).__name__}.",
                    source="scraping_proxy",
                    data=[],
                )

            records, note = _parse_records(raw)
            if not records:
                return _build_response(
                    status="INVALID",
                    reason=note or "No records could be parsed.",
                    source="scraping_proxy",
                    data=[],
                )

            result = _build_response(
                status="OK",
                reason=note,
                source="scraping_proxy",
                data=records,
            )
            _last_valid_cache = result
            return result

        except requests.exceptions.Timeout:
            last_error = f"Request timed out after {_TIMEOUT_SECONDS}s"
        except requests.exceptions.ConnectionError as exc:
            last_error = f"Connection error: {exc}"
        except requests.exceptions.RequestException as exc:
            last_error = f"Request failed: {exc}"

        if attempt < _MAX_RETRIES:
            _time.sleep(_RETRY_DELAY_SECONDS)

    return _fallback_response(
        f"All {_MAX_RETRIES} fetch attempts failed. Last error: {last_error}"
    )

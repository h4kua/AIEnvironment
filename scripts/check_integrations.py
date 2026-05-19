"""
Integration healthcheck script.

Verifies connectivity to all configured external services.
Secrets are never printed — only presence and a masked prefix are shown.

Exit codes:
  0  — all checks pass (warnings are non-fatal)
  1  — one or more CRITICAL services are unreachable

Usage:
    python scripts/check_integrations.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Load .env from project root (two levels up from scripts/)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH, override=True)
except ImportError:
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(value: str) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


class CheckResult:
    def __init__(self, name: str, ok: bool, *, latency_ms: float | None = None,
                 detail: str = "", critical: bool = False) -> None:
        self.name = name
        self.ok = ok
        self.latency_ms = latency_ms
        self.detail = detail
        self.critical = critical


# ── Individual checks ─────────────────────────────────────────────────────────

def check_postgres() -> CheckResult:
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "flood_ai")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    if not password:
        return CheckResult("PostgreSQL", False, detail="DB_PASSWORD not set", critical=True)
    try:
        import psycopg2
        t0 = time.perf_counter()
        conn = psycopg2.connect(
            host=host, port=int(port), dbname=dbname,
            user=user, password=password, connect_timeout=5,
            sslmode="require",
        )
        conn.cursor().execute("SELECT 1")
        conn.close()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return CheckResult("PostgreSQL", True, latency_ms=ms,
                           detail=f"{host}:{port}/{dbname}", critical=True)
    except ImportError:
        return CheckResult("PostgreSQL", False, detail="psycopg2 not installed", critical=True)
    except Exception as exc:
        return CheckResult("PostgreSQL", False, detail=str(exc)[:120], critical=True)


def check_openweather() -> CheckResult:
    import requests
    key = os.getenv("OPENWEATHER_API_KEY", "")
    if not key:
        return CheckResult("OpenWeather", False, detail="OPENWEATHER_API_KEY not set")
    url = "https://api.openweathermap.org/data/2.5/weather"
    try:
        t0 = time.perf_counter()
        resp = requests.get(url, params={"lat": -6.2088, "lon": 106.8456,
                                         "appid": key, "units": "metric"}, timeout=8)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if resp.status_code == 200:
            city = resp.json().get("name", "?")
            return CheckResult("OpenWeather", True, latency_ms=ms, detail=f"city={city}")
        return CheckResult("OpenWeather", False, latency_ms=ms, detail=f"HTTP {resp.status_code}")
    except Exception as exc:
        return CheckResult("OpenWeather", False, detail=str(exc)[:120])


def check_google_maps() -> CheckResult:
    import requests
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        return CheckResult("Google Maps", False, detail="GOOGLE_MAPS_API_KEY not set")
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        t0 = time.perf_counter()
        resp = requests.get(url, params={"address": "Jakarta, Indonesia", "key": key}, timeout=8)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        data = resp.json()
        status = data.get("status", "UNKNOWN")
        if status == "OK":
            return CheckResult("Google Maps", True, latency_ms=ms, detail="geocode ok")
        return CheckResult("Google Maps", False, latency_ms=ms,
                           detail=f"status={status} {data.get('error_message','')[:60]}")
    except Exception as exc:
        return CheckResult("Google Maps", False, detail=str(exc)[:120])


def check_anthropic() -> CheckResult:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return CheckResult("Anthropic", False, detail="ANTHROPIC_API_KEY not set")
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=key, timeout=10.0)
        t0 = time.perf_counter()
        models = client.models.list()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        count = len(list(models.data))
        return CheckResult("Anthropic", True, latency_ms=ms, detail=f"models={count}")
    except ImportError:
        return CheckResult("Anthropic", False, detail="anthropic not installed")
    except Exception as exc:
        return CheckResult("Anthropic", False, detail=str(exc)[:120])


# ── Runtime wiring table ──────────────────────────────────────────────────────

_ENV_VAR = {
    "PostgreSQL":  "DB_PASSWORD",
    "OpenWeather": "OPENWEATHER_API_KEY",
    "Google Maps": "GOOGLE_MAPS_API_KEY",
    "Anthropic":   "ANTHROPIC_API_KEY",
}

_WIRING = {
    "PostgreSQL":  ("YES", "db/psycopg2_connection.py, db/pipeline_writer.py"),
    "OpenWeather": ("YES", "poskobanjir/services/fetcher.py + perception snapshot"),
    "Google Maps": ("YES", "app/services/routing/route_planner.py:108"),
    "Anthropic":   ("NO ", "app/config/llm_config.py + app/services/llm_client.py (config only)"),
}


# ── Output ────────────────────────────────────────────────────────────────────

def _fmt_result(r: CheckResult) -> str:
    status = "OK  " if r.ok else "FAIL"
    lat = f" {r.latency_ms:>6.0f}ms" if r.latency_ms is not None else "         "
    crit = " [CRITICAL]" if r.critical and not r.ok else ""
    return f"  [{status}]{lat}{crit}  {r.name}: {r.detail}"


def main() -> int:
    print("=" * 64)
    print("  Flood AI -- Integration Healthcheck")
    print("=" * 64)
    print(f"\n  .env loaded from: {_ENV_PATH}")

    print("\nConfigured secrets (masked):")
    for var in ("ANTHROPIC_API_KEY", "OPENWEATHER_API_KEY",
                "GOOGLE_MAPS_API_KEY", "DB_PASSWORD"):
        print(f"  {var}={_mask(os.getenv(var, ''))}")

    print(f"\n  DB_HOST={os.getenv('DB_HOST', '(not set)')}")

    print("\nChecking services...")
    results: list[CheckResult] = [
        check_postgres(),
        check_openweather(),
        check_google_maps(),
        check_anthropic(),
    ]

    print("\nResults:")
    for r in results:
        print(_fmt_result(r))

    print("\nRuntime Wiring:")
    print(f"  {'Service':<16} {'Configured':<12} {'Reachable':<11} {'Integrated':<11} Files")
    print("  " + "-" * 80)
    for r in results:
        configured = "YES" if os.getenv(_ENV_VAR.get(r.name, ""), "") else "NO "
        reachable = "YES" if r.ok else "NO "
        integrated, files = _WIRING.get(r.name, ("?  ", "unknown"))
        print(f"  {r.name:<16} {configured:<12} {reachable:<11} {integrated:<11} {files}")

    critical_failures = [r for r in results if r.critical and not r.ok]
    non_critical_failures = [r for r in results if not r.critical and not r.ok]

    print()
    if critical_failures:
        names = ", ".join(r.name for r in critical_failures)
        print(f"FAILED -- critical service(s) unreachable: {names}")
        return 1
    if non_critical_failures:
        names = ", ".join(r.name for r in non_critical_failures)
        print(f"WARN -- non-critical service(s) unreachable: {names}")
    else:
        print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
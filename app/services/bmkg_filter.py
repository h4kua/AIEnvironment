"""
Deterministic geographic scoping for BMKG CAP alerts.

The realtime Jakarta pipeline must not treat national BMKG alerts as local
evidence. Filtering is lexical by design so it remains explainable and does
not depend on external geocoders at runtime.
"""

from __future__ import annotations


_JAKARTA_TOKENS = (
    "dki jakarta",
    "jakarta",
    "jakarta barat",
    "jakarta pusat",
    "jakarta selatan",
    "jakarta timur",
    "jakarta utara",
    "kepulauan seribu",
)


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").lower().replace("/", " ").split())


def is_jakarta_bmkg_alert(alert: dict) -> bool:
    area_desc = _normalize_text(alert.get("area_desc"))
    if area_desc:
        return any(token in area_desc for token in _JAKARTA_TOKENS)

    composite = _normalize_text(
        " ".join(
            [
                str(alert.get("headline") or ""),
                str(alert.get("description") or ""),
                str(alert.get("instruction") or ""),
            ]
        )
    )
    return any(token in composite for token in _JAKARTA_TOKENS)


def filter_jakarta_bmkg_alerts(alerts: list[dict] | None) -> list[dict]:
    return [alert for alert in (alerts or []) if is_jakarta_bmkg_alert(alert)]

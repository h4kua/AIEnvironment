from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg2.extras import Json

from app.api.dashboard import build_demo_page
from app.api.observability import (
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    get_logger,
    metrics_response,
)
from app.api.security import require_api_key
from app.pipeline.flood_pipeline import FloodDecisionPipeline
from app.realtime_native.bundle import load_runtime_bundle
from app.realtime_native.inference import predict_realtime_native
from app.services.decision_engine import _canonical_default_thresholds
from app.services.prediction_service import predict_realtime
from db.psycopg2_connection import close_pool, pooled_connection

_log = get_logger("flood.api")


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


# ─── Location normalization ───────────────────────────────────────────────────
#
# Bug 1+2 root cause: ``location`` was accepted as either ``str``, ``dict``,
# or ``None`` (see SnapshotIn) but flowed UN-normalised through:
#   * pipeline_writer.execute_pipeline (which rejected non-str with
#     ValidationError(field="location"))
#   * PerceptionAgent.run → get_vulnerability_context (which received a
#     ``dict`` stringified as ``"{'city': 'Jakarta'}"`` → mapping
#     confidence=0.0 → NOT_APPLICABLE BNPB gate).
#
# This normaliser runs ONCE at the API boundary, after Pydantic validation
# but before any pipeline call. Output is always one of the canonical
# 6 kota strings; never None, never a dict, never an unrecognised value.

_VALID_KOTA: frozenset[str] = frozenset({
    "Jakarta Utara",
    "Jakarta Selatan",
    "Jakarta Pusat",
    "Jakarta Timur",
    "Jakarta Barat",
    "Kepulauan Seribu",
})
_DEFAULT_LOCATION = "Jakarta Utara"
# Priority order: ``district`` takes precedence over ``city`` so that a payload
# like ``{"district": "Menteng", "city": "Jakarta"}`` resolves to Jakarta Pusat
# (via kecamatan lookup) rather than the bare "Jakarta" default fallback.
_DICT_LOCATION_KEYS = ("district", "city", "kota", "kecamatan", "name")


def _normalize_location(value: object) -> str:
    """
    Collapse the request ``location`` field to a canonical Jakarta kota string.

    Accepts:
      * ``str``   — used as-is after canonicalisation.
      * ``dict``  — extracts the first non-empty value among
                    ``city`` / ``district`` / ``kota`` / ``name`` /
                    ``kecamatan`` (BNPB context's alias dictionary then
                    resolves kecamatan / kelurahan strings to their kota).
      * ``None``  — defaults to ``_DEFAULT_LOCATION``.

    The result is ALWAYS in ``_VALID_KOTA``. When the input is ambiguous
    (e.g. bare ``"Jakarta"``), the helper falls back to ``_DEFAULT_LOCATION``
    rather than guessing — but only after delegating to
    ``map_to_jakarta_district`` so kecamatan / kelurahan / alias forms
    (``"jaksel"``, ``"Pluit"``, ``"south jakarta"``) resolve correctly.
    """
    if isinstance(value, dict):
        raw = ""
        for key in _DICT_LOCATION_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                raw = candidate
                break
    elif isinstance(value, str):
        raw = value
    else:
        return _DEFAULT_LOCATION

    raw = raw.strip()
    if not raw:
        return _DEFAULT_LOCATION

    # 1) Direct title-case match against the 6 valid kota.
    titled = " ".join(part.capitalize() for part in raw.split())
    if titled in _VALID_KOTA:
        return titled

    # 2) Delegate to the BNPB alias dictionary (kecamatan, kelurahan, abbreviations).
    try:
        from app.services.bnpb_context import (
            MAPPING_CONFIDENCE_THRESHOLD,
            map_to_jakarta_district,
        )
        district, confidence = map_to_jakarta_district(raw)
        if district and confidence >= MAPPING_CONFIDENCE_THRESHOLD and district in _VALID_KOTA:
            return district
    except Exception:  # noqa: BLE001 — defensive: never let import / lookup break the API
        pass

    # 3) Ambiguous (e.g. bare "Jakarta") → safe default. Operators can override
    #    by sending a more specific kota / kecamatan string.
    try:
        _log.info(
            "location_normaliser_fallback",
            input=raw,
            defaulted_to=_DEFAULT_LOCATION,
        )
    except TypeError:
        _log.info(
            "location_normaliser_fallback input=%r defaulted_to=%s",
            raw, _DEFAULT_LOCATION,
        )
    return _DEFAULT_LOCATION


def _is_specific_location(raw: str) -> bool:
    """
    Return True when ``raw`` is specific enough to be useful downstream
    (kecamatan / kelurahan / alias / canonical kota name).

    Used by :class:`SnapshotIn` to decide whether to surface ``location_raw``
    to the perception agent. An ambiguous fallback like bare ``"Jakarta"``
    resolves to the default kota via fallback — propagating it would defeat
    the normalised value, since the BNPB mapper would re-fail on the same
    ambiguous string and yield ``code=NOT_APPLICABLE``.
    """
    if not isinstance(raw, str):
        return False
    cleaned = raw.strip()
    if not cleaned:
        return False
    titled = " ".join(part.capitalize() for part in cleaned.split())
    if titled in _VALID_KOTA:
        return True
    try:
        from app.services.bnpb_context import (
            MAPPING_CONFIDENCE_THRESHOLD,
            map_to_jakarta_district,
        )
        district, confidence = map_to_jakarta_district(cleaned)
        if district and confidence >= MAPPING_CONFIDENCE_THRESHOLD:
            return True
    except Exception:  # noqa: BLE001 — defensive
        pass
    return False


class SnapshotIn(BaseModel):
    """
    Inbound flood snapshot payload.

    The ``location`` field is normalised at validation time via
    :func:`_normalize_location`, so the route handler always sees a canonical
    Jakarta kota string regardless of whether the client sent a ``str``,
    ``dict`` (``{"city": "Jakarta"}`` / ``{"district": "Menteng"}``), or
    omitted the field entirely.

    ``location_raw`` preserves the original specificity (kecamatan / kelurahan
    / dict value) so :mod:`app.agents.perception_agent` can attempt
    kecamatan-level BNPB resolution before falling back to the kota.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fetched_at_utc": "2026-05-18T11:30:00Z",
                "location": "Jakarta Utara",
                "openweather": {
                    "main": {"temp": 27.9, "humidity": 91},
                    "rain": {"1h": 20},
                    "coord": {"lat": -6.2088, "lon": 106.8456},
                },
                "poskobanjir": [
                    {"wilayah": "Jakarta Utara", "tinggi_air": 120, "status": "Siaga 3"}
                ],
                "bmkg_alerts": [
                    {
                        "headline": "Hujan Lebat Jakarta",
                        "severity": "Moderate",
                        "certainty": "Observed",
                        "urgency": "Immediate",
                    }
                ],
            }
        }
    )

    fetched_at_utc: str = Field(..., min_length=1)
    location: str = _DEFAULT_LOCATION
    location_raw: str | None = None
    openweather: dict = Field(default_factory=dict)
    poskobanjir: list = Field(default_factory=list)
    bmkg_alerts: list = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_location(cls, data: object) -> object:
        """
        Normalise ``location`` BEFORE field-level type coercion runs, so a
        ``dict`` or ``None`` input never trips the ``location: str`` constraint.

        Also extracts a string ``location_raw`` for kecamatan-level resolution
        downstream. Never raises — falls back to ``_DEFAULT_LOCATION`` on any
        unrecognised input.
        """
        if not isinstance(data, dict):
            return data

        raw = data.get("location")
        if isinstance(raw, dict):
            for key in _DICT_LOCATION_KEYS:
                candidate = raw.get(key)
                if (
                    isinstance(candidate, str)
                    and candidate.strip()
                    and _is_specific_location(candidate)
                ):
                    data.setdefault("location_raw", candidate)
                    break
        elif isinstance(raw, str) and raw.strip() and _is_specific_location(raw):
            data.setdefault("location_raw", raw)

        data["location"] = _normalize_location(raw)
        return data


def _request_budget_s() -> float:
    try:
        return max(1.0, float(os.getenv("FLOOD_REQUEST_BUDGET_S", "15")))
    except ValueError:
        return 15.0


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _prometheus_fail_fast_enabled() -> bool:
    return _truthy_env("FLOOD_FAIL_FAST_PROMETHEUS")


def _configure_prometheus_instrumentation(
    app: FastAPI,
    instrumentator_cls=None,
) -> None:
    try:
        if instrumentator_cls is None:
            from prometheus_fastapi_instrumentator import Instrumentator as instrumentator_cls  # type: ignore[import-not-found]

        instrumentator_cls(excluded_handlers=["/metrics"]).instrument(app)
    except Exception as exc:
        fail_fast = _prometheus_fail_fast_enabled()
        _log.warning(
            "prometheus_instrumentator_disabled",
            error=str(exc),
            fail_fast=fail_fast,
        )
        if fail_fast:
            raise RuntimeError("Prometheus instrumentation initialization failed") from exc


def _register_middleware(app: FastAPI, middleware_cls, **kwargs) -> None:
    try:
        app.add_middleware(middleware_cls, **kwargs)
    except Exception as exc:
        _log.error(
            "middleware_registration_failed",
            middleware=middleware_cls.__name__,
            error=str(exc),
            exc_info=True,
        )
        raise


def _validate_middleware_stack(app: FastAPI) -> None:
    # Force middleware construction during startup so bad middleware fails
    # loudly before the API starts serving traffic.
    try:
        app.middleware_stack = app.build_middleware_stack()
    except Exception as exc:
        _log.error(
            "middleware_initialization_failed",
            error=str(exc),
            exc_info=True,
        )
        raise


def _log_api_failure(exc: Exception, correlation_id: str) -> None:
    try:
        _log.error(
            "api_failure",
            correlation_id=correlation_id,
            error_type=type(exc).__name__,
            message=str(exc),
            exc_info=True,
        )
        return
    except Exception as log_exc:
        fallback_logger = logging.getLogger("flood.api.fallback")
        try:
            fallback_logger.error(
                "api_failure correlation_id=%s error_type=%s log_error=%s",
                correlation_id,
                type(exc).__name__,
                log_exc,
                exc_info=True,
            )
        except Exception:
            return


def _safe_error_response(exc: Exception, status: int = 500) -> None:
    correlation_id = uuid.uuid4().hex
    _log_api_failure(exc, correlation_id)
    raise HTTPException(
        status_code=status,
        detail={"error": "internal_error", "correlation_id": correlation_id},
    ) from exc


def _reject_non_finite(value: object, path: str = "snapshot") -> None:
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise HTTPException(status_code=422, detail=f"{path} contains non-finite float")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_non_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_non_finite(child, f"{path}[{index}]")


def _response_hash(response: dict) -> str:
    encoded = json.dumps(response, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _get_idempotent_response(key: str | None) -> dict | None:
    if not key:
        return None
    with pooled_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM idempotency_keys
                 WHERE created_at < NOW() - INTERVAL '1 hour'
                """
            )
            cur.execute(
                """
                SELECT response_json
                  FROM idempotency_keys
                 WHERE idempotency_key = %s
                   AND created_at >= NOW() - INTERVAL '1 hour'
                """,
                (key,),
            )
            row = cur.fetchone()
        conn.commit()
    return row[0] if row else None


def _store_idempotent_response(key: str | None, response: dict) -> None:
    if not key:
        return
    with pooled_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO idempotency_keys
                    (idempotency_key, response_hash, response_json, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (idempotency_key) DO UPDATE
                    SET response_hash = EXCLUDED.response_hash,
                        response_json = EXCLUDED.response_json,
                        created_at = EXCLUDED.created_at
                """,
                (key, _response_hash(response), Json(response)),
            )
        conn.commit()


async def _bounded_threadpool(fn, *args, **kwargs):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(fn, *args, **kwargs),
            timeout=_request_budget_s(),
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "request_timeout"},
            headers={"Retry-After": "5"},
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    _validate_middleware_stack(app)
    load_runtime_bundle()
    app.state.pipeline = FloodDecisionPipeline()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="Jakarta Flood Prediction API",
    version="2.0.0",
    description="Realtime flood prediction with 5-stage agentic decision pipeline and flood-aware routing.",
    lifespan=lifespan,
)

_configure_prometheus_instrumentation(app)
_register_middleware(app, RequestIdMiddleware)
_register_middleware(app, SecurityHeadersMiddleware)
_register_middleware(
    app,
    TrustedHostMiddleware,
    allowed_hosts=[
        host.strip()
        for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
        if host.strip()
    ],
)
_register_middleware(
    app,
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readiness() -> dict[str, str]:
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            conn.commit()
        _canonical_default_thresholds()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"not_ready": type(exc).__name__},
        ) from exc


@app.get("/metrics", dependencies=[Depends(require_api_key)])
async def metrics() -> Response:
    return metrics_response()


@app.get("/demo", response_class=HTMLResponse)
async def demo_dashboard(
    request: Request,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> HTMLResponse:
    return await _bounded_threadpool(
        build_demo_page,
        pipeline=request.app.state.pipeline,
        origin=origin,
        destination=destination,
    )


@app.get("/predict/realtime")
async def predict_realtime_endpoint(response: Response) -> dict:
    try:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Mon, 30 Jun 2026 00:00:00 GMT"
        response.headers["Link"] = '</predict/realtime-native>; rel="successor-version"'
        return await _bounded_threadpool(predict_realtime)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)


@app.get("/predict/realtime-native")
async def predict_realtime_native_endpoint() -> dict:
    try:
        return await _bounded_threadpool(predict_realtime_native)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)


@app.post("/predict/agentic", dependencies=[Depends(require_api_key)])
async def predict_agentic_endpoint(
    request: Request,
    snapshot: SnapshotIn,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    try:
        cached = await _bounded_threadpool(_get_idempotent_response, idempotency_key)
        if cached is not None:
            return cached

        # ``SnapshotIn.model_validator`` has already normalised ``location`` to
        # a canonical kota string and captured ``location_raw`` for kecamatan-
        # level BNPB resolution. No further coercion needed here.
        snapshot_dict = _model_to_dict(snapshot)
        _reject_non_finite(snapshot_dict)
        result = await _bounded_threadpool(
            request.app.state.pipeline.run,
            snapshot_dict,
            origin=origin,
            destination=destination,
        )
        await _bounded_threadpool(_store_idempotent_response, idempotency_key, result)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)

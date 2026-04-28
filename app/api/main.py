from typing import Optional

from fastapi import FastAPI, HTTPException


from app.pipeline.flood_pipeline import FloodDecisionPipeline
from app.realtime_native.inference import predict_realtime_native
from app.services.prediction_service import predict_realtime
from app.api.db_endpoints import router as db_router



app = FastAPI(
    title="Jakarta Flood Prediction API",
    version="2.0.0",
    description="Realtime flood prediction with 5-stage agentic decision pipeline and flood-aware routing.",
)

app.include_router(db_router)

_pipeline = FloodDecisionPipeline()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/predict/realtime")
def predict_realtime_endpoint():
    try:
        return predict_realtime()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/predict/realtime-native")
def predict_realtime_native_endpoint():
    try:
        return predict_realtime_native()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/predict/agentic")
def predict_agentic_endpoint(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
):
    """
    5-stage agentic decision pipeline with flood-aware routing.

    Returns explainable, failure-aware, trust-weighted flood risk assessment:
    system_status, confidence_score, dominant_risk_driver, baseline_check,
    failure_modes, and requires_manual_review alongside the core prediction.

    Optional query params:
      - origin:      free-text origin address (e.g. "Monas, Jakarta")
      - destination: free-text destination address (e.g. "Bandara Soekarno-Hatta")

    When both are provided, the response includes a flood-safe route recommendation
    in the `safe_route` field. When risk_level >= WARNING and no coords are given,
    `safe_route` contains a zone advisory instead.
    """
    try:
        return _pipeline.run_from_file(origin=origin, destination=destination)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

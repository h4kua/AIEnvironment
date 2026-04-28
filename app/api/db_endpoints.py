from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from db.config import get_db
from db.repositories.snapshot_repository import SnapshotRepository
from db.repositories.pipeline_run_repository import PipelineRunRepository
from db.repositories.decision_repository import DecisionRepository

router = APIRouter(prefix="/db", tags=["Database"])

# --- SNAPSHOTS ---
@router.post("/snapshots/")
def create_snapshot(
    fetched_at_utc: str,
    openweather: dict = None,
    poskobanjir: list = None,
    bmkg_alerts: list = None,
    location: str = None,
    latitude: float = None,
    longitude: float = None,
    db: Session = Depends(get_db),
):
    repo = SnapshotRepository(db)
    snapshot = repo.create(
        fetched_at_utc=fetched_at_utc,
        openweather=openweather,
        poskobanjir=poskobanjir,
        bmkg_alerts=bmkg_alerts,
        location=location,
        latitude=latitude,
        longitude=longitude,
    )
    return {"id": str(snapshot.id), "hash": snapshot.snapshot_hash}

@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: UUID, db: Session = Depends(get_db)):
    repo = SnapshotRepository(db)
    snap = repo.get_by_id(snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap

# --- PIPELINE RUNS ---
@router.post("/pipeline_runs/")
def create_pipeline_run(
    snapshot_id: UUID = None,
    execution_mode: str = "production",
    origin: str = None,
    destination: str = None,
    db: Session = Depends(get_db),
):
    repo = PipelineRunRepository(db)
    run = repo.create(
        snapshot_id=snapshot_id,
        execution_mode=execution_mode,
        origin=origin,
        destination=destination,
    )
    return {"id": str(run.id)}

@router.get("/pipeline_runs/{run_id}")
def get_pipeline_run(run_id: UUID, db: Session = Depends(get_db)):
    repo = PipelineRunRepository(db)
    run = repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run

# --- DECISIONS ---
@router.post("/decisions/")
def create_decision(
    evaluation_id: UUID,
    pipeline_run_id: UUID = None,
    system_status: str = "OK",
    requires_manual_review: bool = False,
    decision_reason: str = "RISK",
    data_validity: str = "VALID",
    ml_execution_mode: str = "FULL",
    risk_level: str = "SAFE",
    probability: float = 0.0,
    confidence_score: float = 0.0,
    trace: str = "",
    explanation: str = "",
    failure_modes: list = None,
    is_safe_for_automation: bool = True,
    db: Session = Depends(get_db),
):
    repo = DecisionRepository(db)
    decision = repo.create(
        evaluation_id=evaluation_id,
        pipeline_run_id=pipeline_run_id,
        system_status=system_status,
        requires_manual_review=requires_manual_review,
        decision_reason=decision_reason,
        data_validity=data_validity,
        ml_execution_mode=ml_execution_mode,
        risk_level=risk_level,
        probability=probability,
        confidence_score=confidence_score,
        trace=trace,
        explanation=explanation,
        failure_modes=failure_modes,
        is_safe_for_automation=is_safe_for_automation,
    )
    return {"id": str(decision.id)}

@router.get("/decisions/{decision_id}")
def get_decision(decision_id: UUID, db: Session = Depends(get_db)):
    repo = DecisionRepository(db)
    dec = repo.get_by_id(decision_id)
    if not dec:
        raise HTTPException(status_code=404, detail="Decision not found")
    return dec

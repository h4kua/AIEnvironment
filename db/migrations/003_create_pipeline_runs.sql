-- Migration: 003_create_pipeline_runs.sql
-- Description: Full pipeline execution log
-- Created: 2026-04-27
-- Hardened: 2026-05-04 (idempotent, non-destructive, CHECK constraints, wrapped)

BEGIN;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Execution metadata
    execution_mode          VARCHAR(20) DEFAULT 'production'
        CHECK (execution_mode IN ('production','staging','shadow','replay','test')),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    execution_time_ms       INTEGER,

    -- Input reference
    snapshot_id             UUID REFERENCES snapshots(id),

    -- Routing parameters (if provided)
    origin                  VARCHAR(200),
    destination             VARCHAR(200),

    -- Output summary
    final_decision          JSONB,
    system_status           VARCHAR(20)
        CHECK (system_status IS NULL OR system_status IN ('OK','DEGRADED','FAIL','PIPELINE_FAILURE')),
    risk_level              VARCHAR(20)
        CHECK (risk_level IS NULL OR risk_level IN ('SAFE','WARNING','DANGER','UNKNOWN')),
    confidence_score        DECIMAL(5, 4)
        CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),

    -- Error tracking
    error_stage             VARCHAR(30),
    error_message           TEXT,
    is_emergency_output     BOOLEAN DEFAULT FALSE,

    -- Metadata
    api_version             VARCHAR(20),
    pipeline_version        VARCHAR(20),

    CONSTRAINT pipeline_runs_completed_check
        CHECK (completed_at IS NULL OR completed_at > started_at)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started   ON pipeline_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_snapshot  ON pipeline_runs(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status    ON pipeline_runs(system_status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_risk      ON pipeline_runs(risk_level);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_execution ON pipeline_runs(execution_mode);

COMMENT ON TABLE pipeline_runs IS 'Complete pipeline execution log for auditing and replay';

COMMIT;

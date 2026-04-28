-- Migration: 009_create_failure_logs.sql
-- Description: All failures detected across pipeline stages with impact metrics
-- Created: 2026-04-27

DROP TABLE IF EXISTS failure_logs CASCADE;

CREATE TABLE failure_logs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pipeline_run_id     UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    
    -- Failure identification
    failure_type       VARCHAR(50) NOT NULL,
    severity           VARCHAR(20) NOT NULL,
    
    -- Failure details
    message            TEXT NOT NULL,
    detail             JSONB,
    
    -- Impact assessment
    confidence_penalty DECIMAL(5, 4) NOT NULL,
    risk_escalation    BOOLEAN NOT NULL,
    
    -- Source tracking
    detection_stage    VARCHAR(30),
    detection_agent    VARCHAR(30),
    
    -- Temporal data
    detected_at        TIMESTAMPTZ DEFAULT NOW(),
    snapshot_fetched_at TIMESTAMPTZ,
    
    -- Context
    snapshot_id        UUID REFERENCES snapshots(id)
);

CREATE INDEX idx_failure_run ON failure_logs(pipeline_run_id);
CREATE INDEX idx_failure_type ON failure_logs(failure_type);
CREATE INDEX idx_failure_severity ON failure_logs(severity);
CREATE INDEX idx_failure_detected ON failure_logs(detected_at DESC);

COMMENT ON TABLE failure_logs IS 'All failures detected across pipeline stages with impact metrics';
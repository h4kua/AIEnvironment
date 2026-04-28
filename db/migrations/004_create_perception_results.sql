-- Migration: 004_create_perception_results.sql
-- Description: Stage 1 output: parsed and validated snapshot with signal detection
-- Created: 2026-04-27

DROP TABLE IF EXISTS perception_results CASCADE;

CREATE TABLE perception_results (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_id             UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    pipeline_run_id         UUID REFERENCES pipeline_runs(id),
    
    -- Agent metadata
    agent_name              VARCHAR(20) DEFAULT 'PerceptionAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- Perception output fields
    data_freshness_minutes  DECIMAL(8, 2) NOT NULL,
    snapshot_completeness   DECIMAL(5, 4) NOT NULL,
    
    -- Signal presence
    signal_presence         JSONB NOT NULL,
    
    -- Raw features
    raw_features            JSONB,
    
    -- Plausibility assessment
    plausibility_score      DECIMAL(5, 4),
    plausibility_details    JSONB,
    
    -- Hydrology assessment
    hydrology_assessment    JSONB,
    
    -- Warnings
    perception_warnings     JSONB,
    
    -- BNPB context
    vulnerability_context   JSONB,
    mapping_info            JSONB,
    
    -- Full snapshot for replay
    processed_snapshot      JSONB
);

CREATE INDEX idx_perception_snapshot ON perception_results(snapshot_id);
CREATE INDEX idx_perception_run ON perception_results(pipeline_run_id);
CREATE INDEX idx_perception_executed ON perception_results(executed_at DESC);

COMMENT ON TABLE perception_results IS 'Stage 1 output: parsed and validated snapshot with signal detection';
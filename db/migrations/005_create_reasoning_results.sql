-- Migration: 005_create_reasoning_results.sql
-- Description: Stage 2 output: ML inference, baseline comparison, failure detection
-- Created: 2026-04-27

DROP TABLE IF EXISTS reasoning_results CASCADE;

CREATE TABLE reasoning_results (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    perception_id           UUID NOT NULL REFERENCES perception_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID REFERENCES pipeline_runs(id),
    
    -- Agent metadata
    agent_name              VARCHAR(20) DEFAULT 'ReasoningAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- ML model output
    model_variant           VARCHAR(30),
    probability             DECIMAL(5, 4) NOT NULL,
    confidence_score        DECIMAL(5, 4) NOT NULL,
    
    -- OOD detection
    ood_detection           JSONB,
    
    -- Feature engineering
    features                JSONB,
    diagnostics             JSONB,
    
    -- Signal extraction
    signals                 JSONB,
    dominant_driver         VARCHAR(50),
    
    -- Context and interpretation
    context_summary         JSONB,
    risk_interpretation     TEXT,
    
    -- Failure modes
    failure_modes           JSONB,
    
    -- Baseline comparison
    baseline_result         JSONB,
    
    -- Model metadata
    model_name              VARCHAR(100)
);

CREATE INDEX idx_reasoning_perception ON reasoning_results(perception_id);
CREATE INDEX idx_reasoning_run ON reasoning_results(pipeline_run_id);
CREATE INDEX idx_reasoning_probability ON reasoning_results(probability);
CREATE INDEX idx_reasoning_driver ON reasoning_results(dominant_driver);

COMMENT ON TABLE reasoning_results IS 'Stage 2 output: ML inference, baseline comparison, failure detection';
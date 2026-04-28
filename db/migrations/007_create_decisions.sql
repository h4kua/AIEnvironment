-- Migration: 007_create_decisions.sql
-- Description: Stage 4 output: final canonical decision report
-- Created: 2026-04-27

DROP TABLE IF EXISTS decisions CASCADE;

CREATE TABLE decisions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evaluation_id           UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID REFERENCES pipeline_runs(id),
    
    -- Decision authority
    _decision_authority     VARCHAR(20),
    _authoritative_fields   JSONB,
    
    -- System health
    system_status           VARCHAR(20) NOT NULL,
    requires_manual_review  BOOLEAN NOT NULL,
    
    -- Disambiguation layer
    decision_reason         VARCHAR(20) NOT NULL,
    data_validity           VARCHAR(20) NOT NULL,
    ml_execution_mode       VARCHAR(20) NOT NULL,
    
    -- Core decision
    risk_level              VARCHAR(20) NOT NULL,
    probability             DECIMAL(5, 4) NOT NULL,
    confidence_score        DECIMAL(5, 4) NOT NULL,
    
    -- Explainability
    trace                   TEXT,
    explanation             TEXT,
    decision_explanation    TEXT,
    
    -- Failure modes
    failure_modes           JSONB,
    
    -- Routing
    safe_route              JSONB,
    tma_data                JSONB,
    
    -- Trend analysis
    trend_analysis          JSONB,
    
    -- BNPB context
    bnpb_advisory           JSONB,
    bnpb_active              BOOLEAN,
    
    -- Additional metadata
    is_safe_for_automation   BOOLEAN NOT NULL,
    
    -- Timestamps
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    decision_timestamp      TIMESTAMPTZ
);

CREATE INDEX idx_decisions_evaluation ON decisions(evaluation_id);
CREATE INDEX idx_decisions_run ON decisions(pipeline_run_id);
CREATE INDEX idx_decisions_risk ON decisions(risk_level);
CREATE INDEX idx_decisions_status ON decisions(system_status);
CREATE INDEX idx_decisions_created ON decisions(created_at DESC);
CREATE INDEX idx_decisions_reason ON decisions(decision_reason);

COMMENT ON TABLE decisions IS 'Stage 4 output: final canonical decision report returned to API consumers';
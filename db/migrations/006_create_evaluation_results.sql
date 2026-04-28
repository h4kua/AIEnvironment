-- Migration: 006_create_evaluation_results.sql
-- Description: Stage 3 output: trust-weighted assessment with failure penalties
-- Created: 2026-04-27

DROP TABLE IF EXISTS evaluation_results CASCADE;

CREATE TABLE evaluation_results (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reasoning_id            UUID NOT NULL REFERENCES reasoning_results(id) ON DELETE CASCADE,
    perception_id           UUID NOT NULL REFERENCES perception_results(id) ON DELETE CASCADE,
    pipeline_run_id         UUID REFERENCES pipeline_runs(id),
    
    -- Agent metadata
    agent_name              VARCHAR(20) DEFAULT 'EvaluationAgent',
    executed_at             TIMESTAMPTZ DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- Core evaluation fields
    system_status           VARCHAR(20) NOT NULL,
    risk_level              VARCHAR(20) NOT NULL,
    probability             DECIMAL(5, 4) NOT NULL,
    confidence_score        DECIMAL(5, 4) NOT NULL,
    
    -- Data quality
    data_freshness_minutes  DECIMAL(8, 2),
    
    -- Risk assessment
    dominant_risk_driver    VARCHAR(50),
    risk_interpretation     TEXT,
    recommended_action      JSONB,
    
    -- Failure tracking
    failure_modes           JSONB,
    baseline_check          JSONB,
    
    -- Manual review decision
    requires_manual_review     BOOLEAN NOT NULL,
    requires_manual_review_reason VARCHAR(500),
    requires_manual_review_meta JSONB,
    
    -- Trust breakdown
    trust_breakdown         JSONB,
    
    -- Decision engine output
    decision                JSONB,
    
    -- BNPB InaRISK integration
    bnpb_active             BOOLEAN,
    bnpb_status             JSONB,
    bnpb_influence          JSONB,
    bnpb_attribution        JSONB,
    bnpb_trace              JSONB,
    
    -- Hydrology
    hydrology_assessment    JSONB,
    
    -- Vulnerability context
    vulnerability_context   JSONB,
    mapping_info            JSONB,
    
    -- Novelty detection
    novelty_advisory        VARCHAR(200),
    
    -- Risk state
    risk_state              JSONB,
    
    -- Plausibility
    plausibility            JSONB
);

CREATE INDEX idx_evaluation_reasoning ON evaluation_results(reasoning_id);
CREATE INDEX idx_evaluation_run ON evaluation_results(pipeline_run_id);
CREATE INDEX idx_evaluation_status ON evaluation_results(system_status);
CREATE INDEX idx_evaluation_risk ON evaluation_results(risk_level);
CREATE INDEX idx_evaluation_confidence ON evaluation_results(confidence_score);

COMMENT ON TABLE evaluation_results IS 'Stage 3 output: trust-weighted assessment with failure penalties';
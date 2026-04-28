-- Migration: 008_create_trust_breakdowns.sql
-- Description: Three-factor trust decomposition for explainability
-- Created: 2026-04-27

DROP TABLE IF EXISTS trust_breakdowns CASCADE;

CREATE TABLE trust_breakdowns (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evaluation_id             UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,
    
    -- Three-factor trust decomposition (all 0.0-1.0)
    model_confidence_factor   DECIMAL(5, 4) NOT NULL,
    data_quality_factor       DECIMAL(5, 4) NOT NULL,
    signal_agreement_factor  DECIMAL(5, 4) NOT NULL,
    
    -- Composite score
    composite_trust          DECIMAL(5, 4) NOT NULL,
    is_low_trust             BOOLEAN NOT NULL,
    
    -- Diagnostic
    dominant_trust_issue     VARCHAR(30),
    
    -- Factor weights used (for audit)
    factor_weights           JSONB,
    
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trust_evaluation ON trust_breakdowns(evaluation_id);
CREATE INDEX idx_trust_composite ON trust_breakdowns(composite_trust);
CREATE INDEX idx_trust_low ON trust_breakdowns(is_low_trust);

COMMENT ON TABLE trust_breakdowns IS 'Three-factor trust decomposition for explainability';
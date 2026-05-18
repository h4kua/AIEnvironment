-- Migration: 008_create_trust_breakdowns.sql
-- Description: Three-factor trust decomposition for explainability
-- Created: 2026-04-27
-- Hardened: 2026-05-04 (idempotent, non-destructive, wrapped in transaction)

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS trust_breakdowns (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evaluation_id             UUID NOT NULL REFERENCES evaluation_results(id) ON DELETE CASCADE,

    -- Three-factor trust decomposition (all 0.0-1.0)
    model_confidence_factor   DECIMAL(5, 4) NOT NULL
        CHECK (model_confidence_factor BETWEEN 0 AND 1),
    data_quality_factor       DECIMAL(5, 4) NOT NULL
        CHECK (data_quality_factor BETWEEN 0 AND 1),
    signal_agreement_factor   DECIMAL(5, 4) NOT NULL
        CHECK (signal_agreement_factor BETWEEN 0 AND 1),

    -- Composite score
    composite_trust           DECIMAL(5, 4) NOT NULL
        CHECK (composite_trust BETWEEN 0 AND 1),
    is_low_trust              BOOLEAN NOT NULL,

    -- Diagnostic
    dominant_trust_issue      VARCHAR(30),

    -- Factor weights used (for audit)
    factor_weights            JSONB,

    created_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trust_evaluation ON trust_breakdowns(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_trust_composite  ON trust_breakdowns(composite_trust);
CREATE INDEX IF NOT EXISTS idx_trust_low        ON trust_breakdowns(is_low_trust);

COMMENT ON TABLE trust_breakdowns IS 'Three-factor trust decomposition for explainability';

COMMIT;

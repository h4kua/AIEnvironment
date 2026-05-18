-- Migration: 011_create_ground_truth_outcomes.sql
-- Description: Ground truth vs prediction comparison
-- Created: 2026-04-27
-- Hardened: 2026-05-04 (idempotent, non-destructive, CHECK constraints, wrapped)

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS ground_truth_outcomes (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Prediction reference
    decision_id             UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    pipeline_run_id         UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,

    -- Ground truth context
    event_date              DATE NOT NULL,
    district                VARCHAR(100) NOT NULL,

    -- Ground truth labels
    is_known_event          BOOLEAN NOT NULL,
    historical_severity     DECIMAL(5, 4)
        CHECK (historical_severity IS NULL OR historical_severity BETWEEN 0 AND 1),
    severity_class          VARCHAR(20),
    event_count             INTEGER,

    -- Prediction labels
    predicted_risk          VARCHAR(20)
        CHECK (predicted_risk IS NULL OR predicted_risk IN ('SAFE','WARNING','DANGER','UNKNOWN')),
    predicted_probability   DECIMAL(5, 4)
        CHECK (predicted_probability IS NULL OR predicted_probability BETWEEN 0 AND 1),
    actual_outcome          INTEGER,

    -- Comparison metrics
    prediction_correct      BOOLEAN,
    probability_error       DECIMAL(5, 4),

    -- Data source
    ground_truth_source     VARCHAR(20),

    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outcome_decision   ON ground_truth_outcomes(decision_id);
CREATE INDEX IF NOT EXISTS idx_outcome_event      ON ground_truth_outcomes(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_outcome_district   ON ground_truth_outcomes(district);
CREATE INDEX IF NOT EXISTS idx_outcome_prediction ON ground_truth_outcomes(predicted_risk);

COMMENT ON TABLE ground_truth_outcomes IS 'Ground truth vs prediction comparison for model evaluation';

COMMIT;

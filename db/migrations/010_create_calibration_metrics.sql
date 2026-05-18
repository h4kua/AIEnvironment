-- Migration: 010_create_calibration_metrics.sql
-- Description: Brier score, ECE, MCE tracking over time
-- Created: 2026-04-27
-- Hardened: 2026-05-04 (idempotent, non-destructive, wrapped in transaction)

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS calibration_metrics (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Metric computation context
    computation_period      VARCHAR(20),
    period_start            DATE NOT NULL,
    period_end              DATE NOT NULL,

    -- Sample counts
    total_predictions       INTEGER NOT NULL,
    valid_ground_truth      INTEGER,

    -- Calibration scores
    brier_score             DECIMAL(6, 4),
    ece                     DECIMAL(6, 4),
    mce                     DECIMAL(6, 4),

    -- Interpretation
    brier_interpretation    VARCHAR(20),
    ece_interpretation      VARCHAR(20),

    -- Calibration bins
    calibration_bins        JSONB,

    -- Model version
    model_variant           VARCHAR(30),
    model_version_hash      VARCHAR(64),

    computed_at             TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT calibration_period_unique
        UNIQUE (computation_period, period_start, model_variant)
);

CREATE INDEX IF NOT EXISTS idx_calibration_period ON calibration_metrics(period_start DESC);
CREATE INDEX IF NOT EXISTS idx_calibration_model  ON calibration_metrics(model_variant);

COMMENT ON TABLE calibration_metrics IS 'Brier score, ECE, MCE tracking over time for model reliability';

COMMIT;

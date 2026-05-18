-- Migration: 013_create_scenario_runs.sql
-- Description: Replay test execution results
-- Created: 2026-04-27
-- Hardened: 2026-05-04 (idempotent, non-destructive, CHECK constraints, wrapped)

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS scenario_runs (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scenario_id             UUID NOT NULL REFERENCES replay_scenarios(id) ON DELETE CASCADE,

    -- Execution metadata
    run_timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_time_ms       INTEGER,

    -- Actual output
    actual_decision         JSONB NOT NULL,
    actual_risk             VARCHAR(20)
        CHECK (actual_risk IS NULL OR actual_risk IN ('SAFE','WARNING','DANGER','UNKNOWN')),
    actual_probability      DECIMAL(5, 4)
        CHECK (actual_probability IS NULL OR actual_probability BETWEEN 0 AND 1),
    actual_status           VARCHAR(20)
        CHECK (actual_status IS NULL OR actual_status IN ('OK','DEGRADED','FAIL','PIPELINE_FAILURE')),

    -- Comparison with expected
    risk_match              BOOLEAN,
    probability_error       DECIMAL(5, 4),
    status_match            BOOLEAN,

    -- Pass/fail determination
    test_passed             BOOLEAN NOT NULL,
    failure_reason          TEXT,

    -- Pipeline version used
    pipeline_version        VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_scenario_run_scenario  ON scenario_runs(scenario_id);
CREATE INDEX IF NOT EXISTS idx_scenario_run_timestamp ON scenario_runs(run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_scenario_run_passed    ON scenario_runs(test_passed);

COMMENT ON TABLE scenario_runs IS 'Replay test execution results for regression testing';

COMMIT;

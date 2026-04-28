-- Migration: 013_create_scenario_runs.sql
-- Description: Replay test execution results
-- Created: 2026-04-27

DROP TABLE IF EXISTS scenario_runs CASCADE;

CREATE TABLE scenario_runs (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scenario_id             UUID NOT NULL REFERENCES replay_scenarios(id) ON DELETE CASCADE,
    
    -- Execution metadata
    run_timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_time_ms       INTEGER,
    
    -- Actual output
    actual_decision         JSONB NOT NULL,
    actual_risk             VARCHAR(20),
    actual_probability      DECIMAL(5, 4),
    actual_status           VARCHAR(20),
    
    -- Comparison with expected
    risk_match              BOOLEAN,
    probability_error       DECIMAL(5, 4),
    status_match            BOOLEAN,
    
    -- Pass/fail determination
    test_passed             BOOLEAN NOT NULL,
    failure_reason         TEXT,
    
    -- Pipeline version used
    pipeline_version        VARCHAR(20)
);

CREATE INDEX idx_scenario_run_scenario ON scenario_runs(scenario_id);
CREATE INDEX idx_scenario_run_timestamp ON scenario_runs(run_timestamp DESC);
CREATE INDEX idx_scenario_run_passed ON scenario_runs(test_passed);

COMMENT ON TABLE scenario_runs IS 'Replay test execution results for regression testing';
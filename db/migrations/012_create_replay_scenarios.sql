-- Migration: 012_create_replay_scenarios.sql
-- Description: Historical and synthetic scenarios for replay testing
-- Created: 2026-04-27
-- Hardened: 2026-05-04 (idempotent, non-destructive, CHECK constraints, wrapped)

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS replay_scenarios (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Scenario identification
    scenario_name           VARCHAR(200) NOT NULL,
    scenario_description    TEXT,
    scenario_type           VARCHAR(30),

    -- Temporal context
    scenario_date           DATE,
    district                VARCHAR(100),

    -- Input data
    input_snapshot          JSONB NOT NULL,
    input_hash              VARCHAR(64) NOT NULL,

    -- Expected output
    expected_risk           VARCHAR(20)
        CHECK (expected_risk IS NULL OR expected_risk IN ('SAFE','WARNING','DANGER','UNKNOWN')),
    expected_probability    DECIMAL(5, 4)
        CHECK (expected_probability IS NULL OR expected_probability BETWEEN 0 AND 1),
    expected_status         VARCHAR(20)
        CHECK (expected_status IS NULL OR expected_status IN ('OK','DEGRADED','FAIL','PIPELINE_FAILURE')),

    -- Metadata
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    created_by              VARCHAR(100),
    tags                    JSONB,

    CONSTRAINT replay_scenarios_hash_unique UNIQUE (input_hash)
);

CREATE INDEX IF NOT EXISTS idx_replay_scenarios_name ON replay_scenarios(scenario_name);
CREATE INDEX IF NOT EXISTS idx_replay_scenarios_date ON replay_scenarios(scenario_date);
CREATE INDEX IF NOT EXISTS idx_replay_scenarios_type ON replay_scenarios(scenario_type);
CREATE INDEX IF NOT EXISTS idx_replay_scenarios_hash ON replay_scenarios(input_hash);

COMMENT ON TABLE replay_scenarios IS 'Historical and synthetic scenarios for replay testing';

COMMIT;

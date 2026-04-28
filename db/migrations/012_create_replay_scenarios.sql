-- Migration: 012_create_replay_scenarios.sql
-- Description: Historical and synthetic scenarios for replay testing
-- Created: 2026-04-27

DROP TABLE IF EXISTS replay_scenarios CASCADE;

CREATE TABLE replay_scenarios (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Scenario identification
    scenario_name           VARCHAR(200) NOT NULL,
    scenario_description    TEXT,
    scenario_type           VARCHAR(30),
    
    -- Temporal context
    scenario_date           DATE,
    district                VARCHAR(100),
    
    -- Input data
    input_snapshot         JSONB NOT NULL,
    input_hash              VARCHAR(64) NOT NULL,
    
    -- Expected output
    expected_risk           VARCHAR(20),
    expected_probability    DECIMAL(5, 4),
    expected_status         VARCHAR(20),
    
    -- Metadata
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    created_by              VARCHAR(100),
    tags                    JSONB,
    
    CONSTRAINT replay_scenarios_hash_unique UNIQUE (input_hash)
);

CREATE INDEX idx_replay_scenarios_name ON replay_scenarios(scenario_name);
CREATE INDEX idx_replay_scenarios_date ON replay_scenarios(scenario_date);
CREATE INDEX idx_replay_scenarios_type ON replay_scenarios(scenario_type);
CREATE INDEX idx_replay_scenarios_hash ON replay_scenarios(input_hash);

COMMENT ON TABLE replay_scenarios IS 'Historical and synthetic scenarios for replay testing';
-- Migration: 002_create_snapshot_sources.sql
-- Description: Track individual source responses for each snapshot
-- Created: 2026-04-27

DROP TABLE IF EXISTS snapshot_sources CASCADE;

CREATE TABLE snapshot_sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_id         UUID NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    
    -- Source identification
    source_name         VARCHAR(50) NOT NULL,
    source_type         VARCHAR(20),
    
    -- Source-specific metadata
    source_response_id  VARCHAR(100),
    response_status     INTEGER,
    response_time_ms    INTEGER,
    
    -- Data quality from source
    data_completeness   DECIMAL(5, 4),
    data_freshness      DECIMAL(8, 2),
    
    -- Timestamps
    fetched_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_snapshot_sources_snapshot ON snapshot_sources(snapshot_id);
CREATE INDEX idx_snapshot_sources_name ON snapshot_sources(source_name);

COMMENT ON TABLE snapshot_sources IS 'Track individual source responses for each snapshot';
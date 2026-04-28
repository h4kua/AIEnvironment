-- Migration: 001_create_snapshots.sql
-- Description: Raw input data storage from data sources
-- Created: 2026-04-27

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop table if exists (for clean migration)
DROP TABLE IF EXISTS snapshots CASCADE;

-- Create snapshots table
CREATE TABLE snapshots (
    -- Primary key
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_hash   VARCHAR(64) NOT NULL,
    
    -- Temporal metadata
    fetched_at_utc  TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- Location data
    location        VARCHAR(100),
    latitude        DECIMAL(10, 8),
    longitude       DECIMAL(11, 8),
    
    -- Source data (JSONB for flexibility)
    openweather     JSONB,
    poskobanjir     JSONB,
    bmkg_alerts     JSONB,
    
    -- Data quality indicators
    data_freshness_minutes  DECIMAL(8, 2),
    snapshot_completeness   DECIMAL(5, 4),
    
    -- Processing status
    processing_status       VARCHAR(20) DEFAULT 'pending',
    
    -- Constraints
    CONSTRAINT snapshots_hash_unique UNIQUE (snapshot_hash)
);

-- Indexes for common query patterns
CREATE INDEX idx_snapshots_fetched_at ON snapshots(fetched_at_utc DESC);
CREATE INDEX idx_snapshots_location ON snapshots(location);
CREATE INDEX idx_snapshots_status ON snapshots(processing_status);
CREATE INDEX idx_snapshots_hash ON snapshots(snapshot_hash);

-- Comments
COMMENT ON TABLE snapshots IS 'Raw input snapshots from data sources (OpenWeatherMap, Posko Banjir, BMKG)';
COMMENT ON COLUMN snapshots.snapshot_hash IS 'SHA-256 hash for deduplication';
COMMENT ON COLUMN snapshots.processing_status IS 'pending | processing | completed | failed';
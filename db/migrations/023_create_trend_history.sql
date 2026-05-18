-- Migration: 023_create_trend_history.sql
-- Description: Durable ring buffer for temporal trend analysis (H2A).
--   Replaces the in-process deque in trend_analysis.py with a shared
--   PostgreSQL table so all workers read the same history and L4 trend
--   decisions are deterministic across restarts and processes.
-- Created: 2026-05-16
-- Idempotent, additive only.

BEGIN;

CREATE TABLE IF NOT EXISTS trend_history (
    id                BIGSERIAL     PRIMARY KEY,
    station_id        TEXT          NOT NULL DEFAULT 'default',
    observed_at       TIMESTAMPTZ   NOT NULL,
    probability       DOUBLE PRECISION NOT NULL
                          CHECK (probability BETWEEN 0 AND 1),
    risk_level        TEXT          NOT NULL,
    water_level_ratio DOUBLE PRECISION
                          CHECK (water_level_ratio IS NULL
                              OR water_level_ratio BETWEEN 0 AND 1),
    rainfall_mm       DOUBLE PRECISION
                          CHECK (rainfall_mm IS NULL OR rainfall_mm >= 0),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Primary lookup: bounded history per station ordered newest-first.
CREATE UNIQUE INDEX IF NOT EXISTS uq_trend_history_station_observed
    ON trend_history(station_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_trend_history_station
    ON trend_history(station_id);

-- Note: insert_trend_record() prunes to 8 rows per station after each write,
-- so table cardinality is bounded. A periodic vacuum is still recommended.

COMMENT ON TABLE trend_history IS
    'Bounded (8 rows/station) temporal prediction snapshots for L4 trend analysis. '
    'Written by app/services/trend_analysis.py. Replaces in-process deque (H2A).';

COMMIT;

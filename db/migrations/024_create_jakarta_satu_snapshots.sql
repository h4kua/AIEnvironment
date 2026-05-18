-- Migration: 024_create_jakarta_satu_snapshots.sql
-- Description: Master snapshot table for each Jakarta Satu dashboard scrape run.
--   One row per hourly execution. Stores raw panel texts for full replay safety.
-- Created: 2026-05-16
-- Idempotent, append-only. No destructive operations.

BEGIN;

CREATE TABLE IF NOT EXISTS jakarta_satu_snapshots (
    id                      BIGSERIAL       PRIMARY KEY,
    scraped_at              TIMESTAMPTZ     NOT NULL,
    source_url              TEXT            NOT NULL,
    scrape_duration_ms      INTEGER,
    panels_found            SMALLINT        NOT NULL DEFAULT 0
                                CHECK (panels_found BETWEEN 0 AND 3),

    -- Raw panel texts stored verbatim for replay / parser improvement
    raw_water_gates_text    TEXT,
    raw_rt_impact_text      TEXT,
    raw_area_impact_text    TEXT,

    -- Outcome flags
    scrape_success          BOOLEAN         NOT NULL DEFAULT TRUE,
    warnings                JSONB,

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_snapshots_scraped_at
    ON jakarta_satu_snapshots(scraped_at DESC);

COMMENT ON TABLE jakarta_satu_snapshots IS
    'Master record for each Jakarta Satu dashboard scrape run (DATA-1). '
    'Append-only. Raw panel texts enable parser replay without re-scraping.';

COMMIT;

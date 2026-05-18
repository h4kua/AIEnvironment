-- Migration: 027_create_jakarta_satu_area_impact.sql
-- Description: Flooded area readings from "Luas Wilayah Terdampak" panel.
--   One row per scrape run — a single aggregate figure in km².
-- Created: 2026-05-16
-- Idempotent, append-only.

BEGIN;

CREATE TABLE IF NOT EXISTS jakarta_satu_area_impact (
    id                  BIGSERIAL       PRIMARY KEY,
    snapshot_id         BIGINT          NOT NULL
                            REFERENCES jakarta_satu_snapshots(id) ON DELETE CASCADE,
    scraped_at          TIMESTAMPTZ     NOT NULL,

    flooded_area_km2    DOUBLE PRECISION,   -- NULL when panel missing or unparseable

    raw_payload         JSONB           NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_area_impact_snapshot
    ON jakarta_satu_area_impact(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_area_impact_scraped_at
    ON jakarta_satu_area_impact(scraped_at DESC);

COMMENT ON TABLE jakarta_satu_area_impact IS
    'Aggregate flooded area (km²) per scrape run. '
    'Source: Luas Wilayah Terdampak Banjir panel on Jakarta Satu dashboard.';

COMMIT;

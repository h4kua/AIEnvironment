-- Migration: 026_create_jakarta_satu_rt_impact.sql
-- Description: Affected residential unit (RT) records from "Daftar RT Terdampak" panel.
--   Each row is one RT entry from one scrape run.
-- Created: 2026-05-16
-- Idempotent, append-only.

BEGIN;

CREATE TABLE IF NOT EXISTS jakarta_satu_rt_impact (
    id              BIGSERIAL       PRIMARY KEY,
    snapshot_id     BIGINT          NOT NULL
                        REFERENCES jakarta_satu_snapshots(id) ON DELETE CASCADE,
    scraped_at      TIMESTAMPTZ     NOT NULL,

    rt_identifier   TEXT,           -- e.g. "001/002"
    kelurahan       TEXT,           -- sub-district name
    kecamatan       TEXT,           -- district name
    wilayah         TEXT,           -- Jakarta region (Timur / Selatan / etc.)

    raw_payload     JSONB           NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_rt_impact_snapshot
    ON jakarta_satu_rt_impact(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_rt_impact_scraped_at
    ON jakarta_satu_rt_impact(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_rt_impact_wilayah
    ON jakarta_satu_rt_impact(wilayah, scraped_at DESC);

COMMENT ON TABLE jakarta_satu_rt_impact IS
    'Affected RT (residential unit) records per scrape run. '
    'Source: Daftar RT Terdampak Banjir panel on Jakarta Satu dashboard.';

COMMIT;

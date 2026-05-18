-- Migration: 025_create_jakarta_satu_water_gates.sql
-- Description: Normalised water gate readings parsed from "Data Pintu Air" panel.
--   Each row is one gate reading from one scrape run.
-- Created: 2026-05-16
-- Idempotent, append-only.

BEGIN;

CREATE TABLE IF NOT EXISTS jakarta_satu_water_gates (
    id              BIGSERIAL       PRIMARY KEY,
    snapshot_id     BIGINT          NOT NULL
                        REFERENCES jakarta_satu_snapshots(id) ON DELETE CASCADE,
    scraped_at      TIMESTAMPTZ     NOT NULL,

    gate_name       TEXT            NOT NULL,
    water_level_cm  DOUBLE PRECISION,
    status          TEXT,           -- Siaga 1-4 / Normal / Awas / Waspada

    raw_payload     JSONB           NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_water_gates_snapshot
    ON jakarta_satu_water_gates(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_water_gates_scraped_at
    ON jakarta_satu_water_gates(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_jakarta_satu_water_gates_name
    ON jakarta_satu_water_gates(gate_name, scraped_at DESC);

COMMENT ON TABLE jakarta_satu_water_gates IS
    'Parsed water gate readings per scrape run. '
    'Source: Data Pintu Air panel on Jakarta Satu dashboard.';

COMMIT;

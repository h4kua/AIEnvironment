-- Migration: 015_decisions_drift_fix.sql
-- Description: Catch-up migration for live `decisions` table.
--              Adds columns present in 007 but missing in production DB.
-- Created: 2026-05-04
-- Idempotent (ADD COLUMN IF NOT EXISTS), non-destructive, additive only.

BEGIN;

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS _authoritative_fields JSONB,
    ADD COLUMN IF NOT EXISTS _decision_authority   VARCHAR(20),
    ADD COLUMN IF NOT EXISTS bnpb_active           BOOLEAN,
    ADD COLUMN IF NOT EXISTS bnpb_advisory         JSONB,
    ADD COLUMN IF NOT EXISTS decision_explanation  TEXT,
    ADD COLUMN IF NOT EXISTS decision_timestamp    TIMESTAMPTZ;

COMMIT;

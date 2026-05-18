-- Migration: 016_trust_breakdowns_drift_fix.sql
-- Description: Catch-up migration for live `trust_breakdowns` table.
--              Adds 1 column present in 008 but missing in production DB.
-- Created: 2026-05-04
-- Idempotent (ADD COLUMN IF NOT EXISTS), non-destructive, additive only.

BEGIN;

ALTER TABLE trust_breakdowns
    ADD COLUMN IF NOT EXISTS factor_weights JSONB;

COMMIT;

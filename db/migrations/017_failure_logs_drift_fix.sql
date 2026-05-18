-- Migration: 017_failure_logs_drift_fix.sql
-- Description: Catch-up migration for live `failure_logs` table.
--              Adds 2 columns present in 009 but missing in production DB.
-- Created: 2026-05-04
-- Idempotent (ADD COLUMN IF NOT EXISTS), non-destructive, additive only.

BEGIN;

ALTER TABLE failure_logs
    ADD COLUMN IF NOT EXISTS detection_agent     VARCHAR(30),
    ADD COLUMN IF NOT EXISTS snapshot_fetched_at TIMESTAMPTZ;

COMMIT;

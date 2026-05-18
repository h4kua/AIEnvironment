-- Migration: 014_evaluation_results_drift_fix.sql
-- Description: Catch-up migration for live `evaluation_results` table.
--              Adds 12 columns present in 006 but missing in production DB.
-- Created: 2026-05-04
-- Idempotent (ADD COLUMN IF NOT EXISTS), non-destructive, additive only.

BEGIN;

ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS bnpb_active                 BOOLEAN,
    ADD COLUMN IF NOT EXISTS bnpb_attribution            JSONB,
    ADD COLUMN IF NOT EXISTS bnpb_influence              JSONB,
    ADD COLUMN IF NOT EXISTS bnpb_status                 JSONB,
    ADD COLUMN IF NOT EXISTS bnpb_trace                  JSONB,
    ADD COLUMN IF NOT EXISTS hydrology_assessment        JSONB,
    ADD COLUMN IF NOT EXISTS mapping_info                JSONB,
    ADD COLUMN IF NOT EXISTS novelty_advisory            VARCHAR(200),
    ADD COLUMN IF NOT EXISTS plausibility                JSONB,
    ADD COLUMN IF NOT EXISTS requires_manual_review_meta JSONB,
    ADD COLUMN IF NOT EXISTS risk_state                  JSONB,
    ADD COLUMN IF NOT EXISTS vulnerability_context       JSONB;

COMMIT;

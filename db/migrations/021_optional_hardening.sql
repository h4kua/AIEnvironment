-- Migration: 021_optional_hardening.sql
-- Description: Section C — OPTIONAL hardening. JSONB GIN indexes, enum
--              tightening, append-only triggers on audit tables,
--              error_message length cap, composite indexes for common
--              ORDER BY patterns, ingestion-worker partial index.
-- Created: 2026-05-04
-- Idempotent, additive only. No DROP/TRUNCATE.

BEGIN;

-- =========================================================================
-- C1. JSONB GIN indexes (jsonb_path_ops is smaller and faster for @>, @?, @@)
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_snapshots_openweather_gin
    ON snapshots USING GIN (openweather jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_snapshots_poskobanjir_gin
    ON snapshots USING GIN (poskobanjir jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_snapshots_bmkg_alerts_gin
    ON snapshots USING GIN (bmkg_alerts jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_decisions_failure_modes_gin
    ON decisions USING GIN (failure_modes jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_evaluation_failure_modes_gin
    ON evaluation_results USING GIN (failure_modes jsonb_path_ops);

-- =========================================================================
-- C2. Enum tightening for free-text columns with a fixed app-level vocabulary
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE decisions ADD CONSTRAINT decisions_authority_chk
        CHECK (_decision_authority IS NULL OR _decision_authority IN (
            'L0_PHYSICAL','L1_SIAGA','L1_5_MULTI','L2_INTEGRITY',
            'L3_ML','L4_TREND','SHADOW'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE ground_truth_outcomes ADD CONSTRAINT outcome_severity_class_chk
        CHECK (severity_class IS NULL OR severity_class IN (
            'mild','moderate','severe','catastrophic'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE ground_truth_outcomes ADD CONSTRAINT outcome_source_chk
        CHECK (ground_truth_source IS NULL OR ground_truth_source IN (
            'BPBD_DKI','BNPB','manual','news_aggregation'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE replay_scenarios ADD CONSTRAINT scenario_type_chk
        CHECK (scenario_type IS NULL OR scenario_type IN (
            'historical','synthetic','adversarial','regression'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_period_kind_chk
        CHECK (computation_period IS NULL OR computation_period IN (
            'daily','weekly','monthly','quarterly'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE snapshot_sources ADD CONSTRAINT snapshot_sources_type_chk
        CHECK (source_type IS NULL OR source_type IN (
            'api','scrape','manual','feed'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- C3. Append-only enforcement on audit tables (decisions, ground_truth_outcomes)
-- =========================================================================
CREATE OR REPLACE FUNCTION raise_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Table % is append-only; UPDATE/DELETE not allowed', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    CREATE TRIGGER decisions_immutable
        BEFORE UPDATE OR DELETE ON decisions
        FOR EACH ROW EXECUTE FUNCTION raise_immutable();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TRIGGER ground_truth_immutable
        BEFORE UPDATE OR DELETE ON ground_truth_outcomes
        FOR EACH ROW EXECUTE FUNCTION raise_immutable();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- C4. Safety limit on pipeline_runs.error_message (prevents stack-trace bloat)
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_error_msg_len_chk
        CHECK (error_message IS NULL OR length(error_message) <= 4000);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- C5. Composite indexes for hot status+time queries
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_decisions_status_created
    ON decisions(system_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_status_executed
    ON evaluation_results(system_status, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status_started
    ON pipeline_runs(system_status, started_at DESC);

-- =========================================================================
-- C6. Worker partial index for ingestion poller
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_snapshots_pending
    ON snapshots(created_at)
    WHERE processing_status = 'pending';

COMMIT;

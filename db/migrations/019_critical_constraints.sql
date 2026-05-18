-- Migration: 019_critical_constraints.sql
-- Description: Section A — CRITICAL constraints. Anti-duplication uniqueness,
--              missing FK indexes, BIGINT overflow fix, decision_timestamp
--              hardening, geo bounds, numeric bounds, calibration validation.
-- Created: 2026-05-04
-- Idempotent, additive only. No DROP/TRUNCATE.

BEGIN;

-- =========================================================================
-- A1-A3. Anti-duplication UNIQUE indexes (one row per pipeline_run / evaluation)
-- =========================================================================
CREATE UNIQUE INDEX IF NOT EXISTS uq_decisions_pipeline_run
    ON decisions(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_decisions_evaluation
    ON decisions(evaluation_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evaluation_pipeline_run
    ON evaluation_results(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_perception_pipeline_run
    ON perception_results(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_reasoning_pipeline_run
    ON reasoning_results(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_trust_evaluation
    ON trust_breakdowns(evaluation_id);

-- =========================================================================
-- A4. Missing FK indexes (cascade-delete becomes seq-scan without these)
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_failure_logs_snapshot
    ON failure_logs(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_outcome_pipeline_run
    ON ground_truth_outcomes(pipeline_run_id);

-- =========================================================================
-- A5. decisions.decision_timestamp: backfill + NOT NULL + not-future CHECK
-- =========================================================================
UPDATE decisions
   SET decision_timestamp = COALESCE(decision_timestamp, created_at, NOW())
 WHERE decision_timestamp IS NULL;

DO $$ BEGIN
    ALTER TABLE decisions ALTER COLUMN decision_timestamp SET NOT NULL;
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE decisions ADD CONSTRAINT decisions_timestamp_not_future_chk
        CHECK (decision_timestamp <= NOW() + INTERVAL '5 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- A6. INTEGER → BIGINT (24-day overflow prevention)
-- =========================================================================
-- ALTER ... TYPE BIGINT is a no-op when column is already BIGINT.
ALTER TABLE pipeline_runs       ALTER COLUMN execution_time_ms TYPE BIGINT;
ALTER TABLE perception_results  ALTER COLUMN execution_time_ms TYPE BIGINT;
ALTER TABLE reasoning_results   ALTER COLUMN execution_time_ms TYPE BIGINT;
ALTER TABLE evaluation_results  ALTER COLUMN execution_time_ms TYPE BIGINT;
ALTER TABLE scenario_runs       ALTER COLUMN execution_time_ms TYPE BIGINT;
ALTER TABLE schema_migrations   ALTER COLUMN duration_ms       TYPE BIGINT;

-- =========================================================================
-- A7. ground_truth_outcomes.actual_outcome MUST be 0 or 1 (binary label)
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE ground_truth_outcomes ADD CONSTRAINT outcome_binary_chk
        CHECK (actual_outcome IS NULL OR actual_outcome IN (0, 1));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- A8. snapshots.latitude / longitude geographic bounds
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE snapshots ADD CONSTRAINT snapshots_lat_chk
        CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE snapshots ADD CONSTRAINT snapshots_lon_chk
        CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- A9. Numeric bounds enforcement (completeness, freshness, http, response time)
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE snapshots ADD CONSTRAINT snapshots_completeness_chk
        CHECK (snapshot_completeness IS NULL OR snapshot_completeness BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE snapshots ADD CONSTRAINT snapshots_freshness_chk
        CHECK (data_freshness_minutes IS NULL OR data_freshness_minutes >= -1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE snapshot_sources ADD CONSTRAINT snapshot_sources_completeness_chk
        CHECK (data_completeness IS NULL OR data_completeness BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE snapshot_sources ADD CONSTRAINT snapshot_sources_freshness_chk
        CHECK (data_freshness IS NULL OR data_freshness >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE snapshot_sources ADD CONSTRAINT snapshot_sources_status_chk
        CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE snapshot_sources ADD CONSTRAINT snapshot_sources_resp_time_chk
        CHECK (response_time_ms IS NULL OR response_time_ms >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE perception_results ADD CONSTRAINT perception_completeness_chk
        CHECK (snapshot_completeness BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE perception_results ADD CONSTRAINT perception_freshness_chk
        CHECK (data_freshness_minutes >= -1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE perception_results ADD CONSTRAINT perception_plausibility_chk
        CHECK (plausibility_score IS NULL OR plausibility_score BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- A10. calibration_metrics validation
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_period_order_chk
        CHECK (period_end >= period_start);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_predictions_chk
        CHECK (total_predictions >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_valid_gt_chk
        CHECK (valid_ground_truth IS NULL OR valid_ground_truth >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_brier_chk
        CHECK (brier_score IS NULL OR brier_score BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_ece_chk
        CHECK (ece IS NULL OR ece BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    ALTER TABLE calibration_metrics ADD CONSTRAINT calibration_mce_chk
        CHECK (mce IS NULL OR mce BETWEEN 0 AND 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMIT;

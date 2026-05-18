-- Migration: 020_high_priority_indexes_and_fks.sql
-- Description: Section B — HIGH PRIORITY hardening. Anti-duplication composite
--              uniques, FK CASCADE→RESTRICT swaps, performance indexes,
--              redundant index removal (explicit user-approved drops),
--              partial index for boolean, NOT NULL on timestamps, enum CHECKs,
--              scenario_runs invariant.
-- Created: 2026-05-04
-- Idempotent. Index drops are explicit user-approved (Section B).

BEGIN;

-- =========================================================================
-- B1. Composite UNIQUE constraints
-- =========================================================================
CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshot_sources_snapshot_name
    ON snapshot_sources(snapshot_id, source_name);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ground_truth_decision_event_district
    ON ground_truth_outcomes(decision_id, event_date, district);

-- =========================================================================
-- B2-B3. FK CASCADE → RESTRICT (preserve audit trail through retention sweeps)
-- DROP CONSTRAINT IF EXISTS + re-ADD is idempotent: re-running converges to
-- the desired RESTRICT state.
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_evaluation_id_fkey;
    ALTER TABLE decisions ADD CONSTRAINT decisions_evaluation_id_fkey
        FOREIGN KEY (evaluation_id) REFERENCES evaluation_results(id) ON DELETE RESTRICT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE ground_truth_outcomes DROP CONSTRAINT IF EXISTS ground_truth_outcomes_decision_id_fkey;
    ALTER TABLE ground_truth_outcomes ADD CONSTRAINT ground_truth_outcomes_decision_id_fkey
        FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE RESTRICT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE ground_truth_outcomes DROP CONSTRAINT IF EXISTS ground_truth_outcomes_pipeline_run_id_fkey;
    ALTER TABLE ground_truth_outcomes ADD CONSTRAINT ground_truth_outcomes_pipeline_run_id_fkey
        FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(id) ON DELETE RESTRICT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- B4. Performance indexes for hot operational queries
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_failure_logs_severity_detected
    ON failure_logs(severity, detected_at DESC)
    WHERE severity IN ('high', 'critical');

CREATE INDEX IF NOT EXISTS idx_failure_logs_run_severity
    ON failure_logs(pipeline_run_id, severity);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_incomplete
    ON pipeline_runs(started_at DESC)
    WHERE completed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_decisions_danger_recent
    ON decisions(created_at DESC)
    WHERE risk_level = 'DANGER';

-- =========================================================================
-- B5. Remove redundant indexes (duplicate of UNIQUE constraint indexes)
-- =========================================================================
DROP INDEX IF EXISTS idx_snapshots_hash;
DROP INDEX IF EXISTS idx_replay_scenarios_hash;

-- =========================================================================
-- B6. Replace boolean index with high-selectivity partial
-- =========================================================================
DROP INDEX IF EXISTS idx_trust_low;
CREATE INDEX IF NOT EXISTS idx_trust_low_partial
    ON trust_breakdowns(evaluation_id)
    WHERE is_low_trust = true;

-- =========================================================================
-- B7. NOT NULL enforcement on every TIMESTAMPTZ column with DEFAULT NOW()
-- Backfill any nulls first (idempotent — UPDATE finds 0 rows on re-run).
-- =========================================================================
UPDATE snapshots             SET created_at  = NOW() WHERE created_at  IS NULL;
UPDATE snapshot_sources      SET fetched_at  = NOW() WHERE fetched_at  IS NULL;
UPDATE perception_results    SET executed_at = NOW() WHERE executed_at IS NULL;
UPDATE reasoning_results     SET executed_at = NOW() WHERE executed_at IS NULL;
UPDATE evaluation_results    SET executed_at = NOW() WHERE executed_at IS NULL;
UPDATE decisions             SET created_at  = NOW() WHERE created_at  IS NULL;
UPDATE trust_breakdowns      SET created_at  = NOW() WHERE created_at  IS NULL;
UPDATE failure_logs          SET detected_at = NOW() WHERE detected_at IS NULL;
UPDATE calibration_metrics   SET computed_at = NOW() WHERE computed_at IS NULL;
UPDATE ground_truth_outcomes SET created_at  = NOW() WHERE created_at  IS NULL;
UPDATE replay_scenarios      SET created_at  = NOW() WHERE created_at  IS NULL;

DO $$ BEGIN ALTER TABLE snapshots             ALTER COLUMN created_at  SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE snapshot_sources      ALTER COLUMN fetched_at  SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE perception_results    ALTER COLUMN executed_at SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE reasoning_results     ALTER COLUMN executed_at SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE evaluation_results    ALTER COLUMN executed_at SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE decisions             ALTER COLUMN created_at  SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE trust_breakdowns      ALTER COLUMN created_at  SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE failure_logs          ALTER COLUMN detected_at SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE calibration_metrics   ALTER COLUMN computed_at SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE ground_truth_outcomes ALTER COLUMN created_at  SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE replay_scenarios      ALTER COLUMN created_at  SET NOT NULL; EXCEPTION WHEN others THEN NULL; END $$;

-- =========================================================================
-- B8. Enum CHECKs for free-text columns emitted as a fixed set
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE reasoning_results ADD CONSTRAINT reasoning_driver_chk
        CHECK (dominant_driver IS NULL OR dominant_driver IN (
            'extreme_rainfall','critical_hydrology','hydrology_stress',
            'compound_event','atmospheric','hydrology_unverified','pipeline_error'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE evaluation_results ADD CONSTRAINT evaluation_driver_chk
        CHECK (dominant_risk_driver IS NULL OR dominant_risk_driver IN (
            'extreme_rainfall','critical_hydrology','hydrology_stress',
            'compound_event','atmospheric','hydrology_unverified','pipeline_error'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE failure_logs ADD CONSTRAINT failure_stage_chk
        CHECK (detection_stage IS NULL OR detection_stage IN (
            'perception','reasoning','evaluation','action','routing','contract'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- B9. scenario_runs: failure_reason required when test_passed = false
-- =========================================================================
DO $$ BEGIN
    ALTER TABLE scenario_runs ADD CONSTRAINT scenario_runs_failure_reason_chk
        CHECK (test_passed = true
               OR (failure_reason IS NOT NULL AND length(trim(failure_reason)) > 0));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMIT;

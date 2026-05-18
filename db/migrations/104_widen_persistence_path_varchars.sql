-- =====================================================================
-- 104_widen_persistence_path_varchars.sql
--
-- Purpose
-- -------
-- Migration 103 widened the obvious columns on
-- pipeline_runs / evaluation_results / decisions, but
-- ``StringDataRightTruncation: value too long for type character
-- varying(30)`` continued to fire because the persistence write also
-- writes to columns on adjacent tables whose widths were never updated
-- to match the post-audit vocabulary:
--
--   reasoning_results.model_variant      varchar(30)
--     Runtime writes "XGBoost Flood Predictor - Realtime Native"
--     (43 chars) → overrun.
--   trust_breakdowns.dominant_trust_issue varchar(30)
--     Reason strings can exceed 30 chars in trust diagnostics.
--   failure_logs.detection_agent / detection_stage  varchar(30)
--     Long stage names ("evaluation_canonical_passthrough") overrun.
--
-- Each ALTER lives in its own DO block so a missing column on an older
-- schema reports a NOTICE and the rest of the batch proceeds.
-- Idempotent: re-running on already-widened columns is a no-op.
-- =====================================================================

DO $$ BEGIN
    ALTER TABLE reasoning_results ALTER COLUMN model_variant TYPE varchar(100);
EXCEPTION WHEN others THEN
    RAISE NOTICE 'skip reasoning_results.model_variant: %', SQLERRM;
END $$;

DO $$ BEGIN
    ALTER TABLE trust_breakdowns ALTER COLUMN dominant_trust_issue TYPE varchar(100);
EXCEPTION WHEN others THEN
    RAISE NOTICE 'skip trust_breakdowns.dominant_trust_issue: %', SQLERRM;
END $$;

DO $$ BEGIN
    ALTER TABLE failure_logs ALTER COLUMN detection_agent TYPE varchar(100);
EXCEPTION WHEN others THEN
    RAISE NOTICE 'skip failure_logs.detection_agent: %', SQLERRM;
END $$;

DO $$ BEGIN
    ALTER TABLE failure_logs ALTER COLUMN detection_stage TYPE varchar(100);
EXCEPTION WHEN others THEN
    RAISE NOTICE 'skip failure_logs.detection_stage: %', SQLERRM;
END $$;

DO $$ BEGIN
    ALTER TABLE calibration_metrics ALTER COLUMN model_variant TYPE varchar(100);
EXCEPTION WHEN others THEN
    RAISE NOTICE 'skip calibration_metrics.model_variant: %', SQLERRM;
END $$;

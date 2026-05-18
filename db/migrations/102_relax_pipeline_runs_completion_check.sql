-- =====================================================================
-- 102_relax_pipeline_runs_completion_check.sql
--
-- Purpose
-- -------
-- The legacy ``pipeline_runs_completed_check`` requires
-- ``completed_at > started_at`` (strictly greater). The
-- determinism-injection work (orchestrator-pinned ``now_utc``) writes
-- the SAME timestamp into both columns so identical-snapshot replays
-- produce byte-identical persistence rows. This relaxes the constraint
-- to ``completed_at >= started_at`` — semantically correct (a pipeline
-- can complete in zero observable wall-clock time when the clock is
-- pinned) and preserves the invariant against backwards-running clocks.
--
-- Idempotent: DROP IF EXISTS then ADD.
-- =====================================================================

DO $$ BEGIN
    ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_completed_check;
    ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_completed_check
        CHECK (completed_at IS NULL OR completed_at >= started_at);
EXCEPTION WHEN others THEN NULL; END $$;

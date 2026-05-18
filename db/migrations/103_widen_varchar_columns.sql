-- =====================================================================
-- 103_widen_varchar_columns.sql
--
-- Purpose
-- -------
-- After 101 + 102 cleared the legacy CHECK-constraint mismatches,
-- persistence still occasionally fails with:
--   StringDataRightTruncation: value too long for type character varying(N)
--
-- The post-audit vocabulary is broader than the original column widths.
-- This migration widens the affected columns to safer limits without
-- changing semantics. ``ALTER COLUMN … TYPE`` keeps existing data
-- (varchar widening is metadata-only when the new limit ≥ old).
--
-- IMPLEMENTATION NOTE
-- -------------------
-- Each column is altered inside its own ``DO`` block with its own
-- ``EXCEPTION WHEN others`` handler. This is deliberate:
--   * Postgres makes a ``DO`` block atomic — if any single ALTER
--     inside one block fails (e.g. the column doesn't exist on this
--     schema), the ENTIRE block is rolled back and the rest of the
--     widenings are silently skipped.
--   * Splitting per-column makes the migration idempotent AND
--     resilient: a missing column produces one NOTICE and the next
--     column still gets widened.
--
-- The column-to-table mapping below reflects the schema as observed
-- via information_schema (decisions owns ml_execution_mode /
-- decision_reason / data_validity; evaluation_results owns agent_name;
-- pipeline_runs has no ml_execution_mode / decision_reason columns).
-- =====================================================================


-- ─── pipeline_runs ───────────────────────────────────────────────────

DO $$ BEGIN
    ALTER TABLE pipeline_runs ALTER COLUMN system_status TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip pipeline_runs.system_status: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs ALTER COLUMN execution_mode TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip pipeline_runs.execution_mode: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs ALTER COLUMN pipeline_version TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip pipeline_runs.pipeline_version: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs ALTER COLUMN api_version TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip pipeline_runs.api_version: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs ALTER COLUMN risk_level TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip pipeline_runs.risk_level: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs ALTER COLUMN error_stage TYPE varchar(100);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip pipeline_runs.error_stage: %', SQLERRM; END $$;


-- ─── evaluation_results ──────────────────────────────────────────────

DO $$ BEGIN
    ALTER TABLE evaluation_results ALTER COLUMN system_status TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip evaluation_results.system_status: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE evaluation_results ALTER COLUMN risk_level TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip evaluation_results.risk_level: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE evaluation_results ALTER COLUMN dominant_risk_driver TYPE varchar(100);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip evaluation_results.dominant_risk_driver: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE evaluation_results ALTER COLUMN agent_name TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip evaluation_results.agent_name: %', SQLERRM; END $$;


-- ─── decisions ───────────────────────────────────────────────────────

DO $$ BEGIN
    ALTER TABLE decisions ALTER COLUMN system_status TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip decisions.system_status: %', SQLERRM; END $$;

-- decisions.risk_level is embedded in matview daily_decision_summary;
-- Postgres refuses ALTER COLUMN TYPE while a matview holds the old type
-- in its stored plan. Drop the matview + its unique index, widen the
-- column, recreate the matview identically. Wrapped in its own DO block
-- with guarded IF EXISTS so a missing matview is a no-op rather than an
-- error. The matview definition is preserved verbatim from
-- pg_get_viewdef.
DO $$ BEGIN
    DROP MATERIALIZED VIEW IF EXISTS public.daily_decision_summary;
    ALTER TABLE decisions ALTER COLUMN risk_level TYPE varchar(50);
    CREATE MATERIALIZED VIEW public.daily_decision_summary AS
        SELECT date(created_at) AS decision_date,
               risk_level,
               count(*) AS total_decisions,
               avg(confidence_score) AS avg_confidence,
               sum(CASE WHEN requires_manual_review THEN 1 ELSE 0 END)
                   AS manual_review_count
          FROM decisions
         GROUP BY date(created_at), risk_level;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_summary
        ON public.daily_decision_summary (decision_date, risk_level);
EXCEPTION WHEN others THEN
    RAISE NOTICE 'skip decisions.risk_level (matview recreate): %', SQLERRM;
END $$;

DO $$ BEGIN
    ALTER TABLE decisions ALTER COLUMN ml_execution_mode TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip decisions.ml_execution_mode: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE decisions ALTER COLUMN data_validity TYPE varchar(100);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip decisions.data_validity: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE decisions ALTER COLUMN decision_reason TYPE varchar(200);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip decisions.decision_reason: %', SQLERRM; END $$;

DO $$ BEGIN
    ALTER TABLE decisions ALTER COLUMN _decision_authority TYPE varchar(50);
EXCEPTION WHEN others THEN RAISE NOTICE 'skip decisions._decision_authority: %', SQLERRM; END $$;

-- =====================================================================
-- 101_drop_legacy_risk_check_constraints.sql
--
-- Purpose
-- -------
-- Migration 100_vocabulary_sync.sql installs ``eval_risk_chk`` /
-- ``decisions_risk_chk`` / ``pipeline_runs_risk_chk`` that accept the
-- full canonical risk vocabulary (SAFE, PRE_ALERT, WARNING, DANGER,
-- UNKNOWN).
--
-- However, live databases provisioned before 100 carry an UNNAMED
-- ``CHECK (risk_level IN (...))`` constraint authored by the original
-- table-create migrations (003 / 006 / 007). PostgreSQL auto-named
-- those constraints ``chk_eval_risk`` / ``chk_decisions_risk`` /
-- ``chk_pipeline_runs_risk`` (the exact name depends on the server's
-- naming policy and the create-order). Because migration 100 only
-- ``DROP CONSTRAINT IF EXISTS eval_risk_chk`` (i.e. it drops by the
-- NEW name, not the legacy auto-generated one), the legacy constraint
-- survives — and PostgreSQL applies the AND of every CHECK on the
-- column, so canonical ``UNKNOWN`` rows are still rejected with:
--
--   CheckViolation: new row for relation "evaluation_results"
--                   violates check constraint "chk_eval_risk"
--
-- This migration walks ``pg_constraint`` for any CHECK whose
-- definition mentions ``risk_level`` and that is NOT in the canonical
-- set installed by migration 100, and drops it. The walk is
-- idempotent and safe to re-run.
--
-- After this migration, the only risk_level CHECK constraints on
-- evaluation_results / decisions / pipeline_runs are the ones
-- authored in 100_vocabulary_sync.sql, which accept the full
-- canonical set.
-- =====================================================================

DO $$
DECLARE
    rec RECORD;
    canonical_names TEXT[] := ARRAY[
        'eval_risk_chk',
        'decisions_risk_chk',
        'pipeline_runs_risk_chk'
    ];
BEGIN
    FOR rec IN
        SELECT con.conname AS constraint_name,
               rel.relname AS table_name
          FROM pg_constraint con
          JOIN pg_class      rel ON rel.oid = con.conrelid
          JOIN pg_namespace  nsp ON nsp.oid = rel.relnamespace
         WHERE nsp.nspname = current_schema()
           AND rel.relname IN (
                   'evaluation_results',
                   'decisions',
                   'pipeline_runs'
               )
           AND con.contype = 'c'
           AND pg_get_constraintdef(con.oid) ILIKE '%risk_level%'
           AND NOT (con.conname = ANY (canonical_names))
    LOOP
        RAISE NOTICE
            'Dropping legacy risk_level CHECK constraint %.% (replaced by migration 100)',
            rec.table_name, rec.constraint_name;
        EXECUTE format(
            'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
            rec.table_name, rec.constraint_name
        );
    END LOOP;
END $$;

-- Reinstall the canonical constraints (idempotent — DROP IF EXISTS then
-- ADD) so this migration is self-contained even when 100 was never
-- applied.
DO $$ BEGIN
    ALTER TABLE evaluation_results DROP CONSTRAINT IF EXISTS eval_risk_chk;
    ALTER TABLE evaluation_results ADD CONSTRAINT eval_risk_chk
        CHECK (risk_level IN ('SAFE','PRE_ALERT','WARNING','DANGER','UNKNOWN'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_risk_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_risk_chk
        CHECK (risk_level IN ('SAFE','PRE_ALERT','WARNING','DANGER','UNKNOWN'));
EXCEPTION WHEN others THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_risk_chk;
    ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_risk_chk
        CHECK (risk_level IS NULL OR risk_level IN
               ('SAFE','PRE_ALERT','WARNING','DANGER','UNKNOWN'));
EXCEPTION WHEN others THEN NULL; END $$;

-- Migration: 022_observation_identity.sql
-- Description: Separate snapshot identity (observation_id) from snapshot
--              content (snapshot_hash). Each acquisition event becomes its
--              own row; identical content is no longer destructively upserted.
--              Adds UNIQUE(snapshot_id) on pipeline_runs to enforce one
--              canonical pipeline_run per snapshot.
-- Created: 2026-05-04
-- Idempotent, additive only. The destructive part (DROP CONSTRAINT on the
-- old hash UNIQUE) is wrapped in DO/EXCEPTION so re-runs are no-ops.

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- 1. Add observation identity columns. Both have safe defaults so existing
--    rows are backfilled with a unique observation_id and first_seen_at
--    derived from created_at (or NOW() if created_at is somehow NULL).
-- ---------------------------------------------------------------------------
ALTER TABLE snapshots
    ADD COLUMN IF NOT EXISTS observation_id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS first_seen_at  TIMESTAMPTZ;

UPDATE snapshots
   SET observation_id = COALESCE(observation_id, gen_random_uuid()),
       first_seen_at  = COALESCE(first_seen_at, created_at, fetched_at_utc, NOW())
 WHERE observation_id IS NULL OR first_seen_at IS NULL;

DO $$ BEGIN
    ALTER TABLE snapshots ALTER COLUMN observation_id SET NOT NULL;
    ALTER TABLE snapshots ALTER COLUMN first_seen_at  SET NOT NULL;
EXCEPTION WHEN others THEN NULL; END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_observation_id
    ON snapshots(observation_id);

CREATE INDEX IF NOT EXISTS idx_snapshots_first_seen_at
    ON snapshots(first_seen_at DESC);

-- ---------------------------------------------------------------------------
-- 2. Demote snapshot_hash from UNIQUE identity to non-unique dedup helper.
--    Plain index replaces the constraint for fast lookup. Idempotent.
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    ALTER TABLE snapshots DROP CONSTRAINT IF EXISTS snapshots_hash_unique;
EXCEPTION WHEN others THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_snapshots_hash_lookup
    ON snapshots(snapshot_hash);

-- ---------------------------------------------------------------------------
-- 3. One pipeline_run per snapshot — kills the "multiple canonical runs"
--    ambiguity. Partial unique because pipeline_runs.snapshot_id is nullable.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_runs_snapshot
    ON pipeline_runs(snapshot_id)
    WHERE snapshot_id IS NOT NULL;

COMMIT;

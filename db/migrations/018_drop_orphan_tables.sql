-- Migration: 018_drop_orphan_tables.sql
-- Description: Remove orphan tables in live DB that have no migration backing
--              and no codebase reference. Verified zero SQL references in
--              app/, db/, scripts/, tests/ as of 2026-05-04.
-- Created: 2026-05-04
-- Idempotent (DROP TABLE IF EXISTS), runs only once meaningfully.

BEGIN;

-- Orphan tables (not in any migration 001..017, no FK into them):
DROP TABLE IF EXISTS predictions  CASCADE;
DROP TABLE IF EXISTS routing_logs CASCADE;
DROP TABLE IF EXISTS sensor_data  CASCADE;
DROP TABLE IF EXISTS trend_logs   CASCADE;

COMMIT;

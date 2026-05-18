-- Migration: 000_schema_migrations.sql
-- Description: Tracking table for applied migrations. Bootstrap file.
-- Created: 2026-05-04

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename     VARCHAR(255) PRIMARY KEY,
    applied_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    sha256       CHAR(64)     NOT NULL,
    success      BOOLEAN      NOT NULL DEFAULT TRUE,
    duration_ms  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
    ON schema_migrations(applied_at DESC);

COMMENT ON TABLE schema_migrations IS
    'Append-only tracking table for db/migrations/*.sql. '
    'filename + sha256 define applied state. '
    'Idempotent runner: skip rows where (filename, sha256, success=true) exists.';

COMMIT;

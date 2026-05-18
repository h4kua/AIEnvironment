"""
Deterministic, replay-safe migration runner (H3).

Algorithm per run:
  1. Bootstrap schema_migrations table if absent (inline DDL, no file needed).
  2. Load applied-migration records from schema_migrations.
  3. Scan db/migrations/*.sql in strict lexical order.
  4. Abort on checksum drift (file modified after application).
  5. Abort on previously-failed migration (success=FALSE in tracking table).
  6. Abort on out-of-order gaps (unapplied file precedes an applied file).
  7. Apply each pending migration with autocommit=True so the file's own
     BEGIN/COMMIT is respected.
  8. Record success or failure to schema_migrations immediately after each
     apply. Stop on first failure; never silently continue.

Thin CLI lives in scripts/run_migrations.py.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from db.psycopg2_connection import Psycopg2ConnectionConfig, get_psycopg2_connection

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Inline DDL so the runner works on a completely fresh DB without needing
# 000_schema_migrations.sql to already be applied.
_BOOTSTRAP_SQL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename     VARCHAR(255) PRIMARY KEY,
    applied_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    sha256       CHAR(64)     NOT NULL,
    success      BOOLEAN      NOT NULL DEFAULT TRUE,
    duration_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
    ON schema_migrations(applied_at DESC);
"""


# ── Domain types ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Migration:
    path: Path
    filename: str
    checksum: str   # hex SHA-256 of file bytes at scan time


class MigrationError(Exception):
    """Unrecoverable migration state. Runner stops; manual intervention required."""


# ── Pure helpers (no DB, fully testable) ─────────────────────────────────────

def sha256_file(path: Path) -> str:
    """Return hex SHA-256 of file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_migrations(migrations_dir: Path = _MIGRATIONS_DIR) -> list[Migration]:
    """Return Migration objects for all *.sql files, sorted lexically by name."""
    files = sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name)
    return [Migration(path=f, filename=f.name, checksum=sha256_file(f)) for f in files]


def detect_gaps(
    migrations: list[Migration],
    applied: dict[str, dict],
) -> list[str]:
    """
    Return filenames of unapplied migrations that are superseded by later
    applied ones. Indicates out-of-order or skipped application.

    Example: [001 applied, 002 NOT applied, 003 applied] -> ['002_...sql']
    """
    gaps: list[str] = []
    for i, m in enumerate(migrations):
        if m.filename in applied:
            continue
        if any(later.filename in applied for later in migrations[i + 1 :]):
            gaps.append(m.filename)
    return gaps


# ── DB operations ─────────────────────────────────────────────────────────────

def bootstrap(conn) -> None:
    """Create schema_migrations if it does not exist. Safe to call every run."""
    prior = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(_BOOTSTRAP_SQL)
    finally:
        conn.autocommit = prior


def load_applied(conn) -> dict[str, dict]:
    """Return schema_migrations rows keyed by filename, ordered by applied_at."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT filename, sha256, success "
            "FROM schema_migrations ORDER BY applied_at ASC"
        )
        rows = cur.fetchall()
    return {row[0]: {"sha256": row[1], "success": bool(row[2])} for row in rows}


def schema_migrations_exists(conn) -> bool:
    """Return True when the tracking table already exists."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = 'schema_migrations'
            )
            """
        )
        row = cur.fetchone()
    return bool(row and row[0])


def apply_migration(conn, migration: Migration) -> int:
    """
    Execute migration SQL with autocommit=True so the file's own BEGIN/COMMIT
    are respected as top-level transactions.

    Returns elapsed milliseconds. Raises on any database error.
    """
    sql = migration.path.read_text(encoding="utf-8")
    prior = conn.autocommit
    conn.autocommit = True
    t0 = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.autocommit = prior
    return round((time.perf_counter() - t0) * 1000)


def record_migration(
    conn,
    filename: str,
    checksum: str,
    success: bool,
    duration_ms: int,
) -> None:
    """Upsert one row into schema_migrations."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO schema_migrations (filename, sha256, success, duration_ms)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (filename) DO UPDATE
              SET sha256      = EXCLUDED.sha256,
                  success     = EXCLUDED.success,
                  duration_ms = EXCLUDED.duration_ms,
                  applied_at  = NOW()
            """,
            (filename, checksum, success, duration_ms),
        )
    conn.commit()


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_migrations(
    config: Optional[Psycopg2ConnectionConfig] = None,
    *,
    dry_run: bool = False,
    verify: bool = False,
    migrations_dir: Path = _MIGRATIONS_DIR,
) -> int:
    """
    Main entry point. Returns POSIX exit code (0 = success, non-zero = error).

    dry_run: print pending migrations without applying them.
    verify:  check checksums of all applied migrations; no apply.
    """
    conn = get_psycopg2_connection(config)
    try:
        # Bootstrap unconditionally — dry-run and verify also need schema_migrations
        # to exist before load_applied() can query it.
        if dry_run:
            applied = load_applied(conn) if schema_migrations_exists(conn) else {}
        else:
            bootstrap(conn)
            applied = load_applied(conn)
        # Close the implicit read transaction opened by load_applied()'s SELECT
        # so apply_migration() can switch conn.autocommit without raising
        # "set_session cannot be used inside a transaction".
        conn.commit()
        migrations = scan_migrations(migrations_dir)

        if verify:
            return _run_verify(migrations, applied)

        # ── Pre-flight: gaps ──────────────────────────────────────────────────
        gaps = detect_gaps(migrations, applied)
        if gaps:
            print("ERROR: unapplied migrations precede applied ones (gap):")
            for g in gaps:
                print(f"  GAP      {g}")
            print("Resolve these gaps before continuing.")
            return 1

        # ── Pre-flight: drift and previous failures ───────────────────────────
        for m in migrations:
            if m.filename not in applied:
                continue
            rec = applied[m.filename]
            if not rec["success"]:
                raise MigrationError(
                    f"{m.filename!r} has success=FALSE in schema_migrations. "
                    "Manual intervention required before re-running."
                )
            if rec["sha256"] != m.checksum:
                raise MigrationError(
                    f"Checksum drift: {m.filename!r} "
                    f"stored={rec['sha256'][:16]}… "
                    f"current={m.checksum[:16]}…"
                )

        # ── Apply pending ─────────────────────────────────────────────────────
        pending = [m for m in migrations if m.filename not in applied]
        if not pending:
            print("All migrations already applied. Nothing to do.")
            return 0

        for m in pending:
            if dry_run:
                print(f"  PENDING  {m.filename}  sha256={m.checksum[:16]}…")
                continue

            print(f"  Applying {m.filename} ...", end=" ", flush=True)
            try:
                duration_ms = apply_migration(conn, m)
                record_migration(conn, m.filename, m.checksum, True, duration_ms)
                print(f"OK ({duration_ms}ms)")
            except Exception as exc:
                print("FAILED")
                try:
                    record_migration(conn, m.filename, m.checksum, False, 0)
                except Exception:
                    pass
                raise MigrationError(
                    f"{m.filename!r} failed. Runner stopped. Cause: {exc}"
                ) from exc

        if dry_run:
            print(f"\n{len(pending)} migration(s) would be applied (dry-run, no changes).")
        else:
            print(f"\n{len(pending)} migration(s) applied.")
        return 0

    finally:
        conn.close()


def _run_verify(
    migrations: list[Migration],
    applied: dict[str, dict],
) -> int:
    n_checked = 0
    n_problems = 0
    for m in migrations:
        if m.filename not in applied:
            print(f"  PENDING  {m.filename}")
            continue
        rec = applied[m.filename]
        n_checked += 1
        if not rec["success"]:
            print(f"  FAILED   {m.filename}  (success=FALSE)")
            n_problems += 1
        elif rec["sha256"] != m.checksum:
            print(
                f"  DRIFT    {m.filename}\n"
                f"           stored ={rec['sha256'][:32]}…\n"
                f"           current={m.checksum[:32]}…"
            )
            n_problems += 1
        else:
            print(f"  OK       {m.filename}")
    print(
        f"\n{n_checked} applied migration(s) checked. "
        f"{n_problems} problem(s) found."
    )
    return 0 if n_problems == 0 else 1

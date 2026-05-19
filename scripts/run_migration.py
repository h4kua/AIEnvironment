"""
Standalone PostgreSQL migration runner for the Flood AI project.

Reads DB credentials from .env (python-dotenv), tracks applied files in the
``schema_migrations`` table (compatible with db/migrations/000_schema_migrations.sql),
and applies pending migrations from ``db/migrations/`` in lexical order.

Usage:
    python run_migration.py                                                # apply all pending
    python run_migration.py --file db/migrations/105_decision_l1_7_safety_floor.sql
    python run_migration.py --status
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import psycopg2
except ImportError:
    sys.stderr.write(
        "ERROR: psycopg2 is not installed. Run:\n"
        "    pip install psycopg2-binary python-dotenv\n"
    )
    sys.exit(2)

try:
    from dotenv import load_dotenv
except ImportError:
    sys.stderr.write(
        "ERROR: python-dotenv is not installed. Run:\n"
        "    pip install psycopg2-binary python-dotenv\n"
    )
    sys.exit(2)


# scripts/ lives one level below the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
ENV_PATH = PROJECT_ROOT / ".env"

BOOTSTRAP_SQL = """\
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


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    name: str
    user: str
    password: str

    def as_psycopg2_kwargs(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "connect_timeout": 10,
            "application_name": "flood-ai-migration-runner",
        }


@dataclass(frozen=True)
class Migration:
    path: Path
    filename: str
    checksum: str


def load_config() -> DbConfig:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()

    try:
        return DbConfig(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            name=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
    except KeyError as missing:
        sys.stderr.write(
            f"ERROR: missing required env var {missing} (check .env at {ENV_PATH}).\n"
        )
        sys.exit(2)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_migrations() -> list[Migration]:
    if not MIGRATIONS_DIR.is_dir():
        sys.stderr.write(f"ERROR: migrations directory not found: {MIGRATIONS_DIR}\n")
        sys.exit(2)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    return [Migration(path=f, filename=f.name, checksum=sha256_file(f)) for f in files]


def connect(cfg: DbConfig):
    try:
        return psycopg2.connect(**cfg.as_psycopg2_kwargs())
    except psycopg2.OperationalError as exc:
        sys.stderr.write(
            "ERROR: cannot connect to PostgreSQL.\n"
            f"  host={cfg.host} port={cfg.port} db={cfg.name} user={cfg.user}\n"
            f"  reason: {exc}\n"
            "Hint: confirm the server is running, password is correct, and pg_hba.conf "
            "allows the connection.\n"
        )
        sys.exit(2)


def bootstrap(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(BOOTSTRAP_SQL)


def load_applied(conn) -> dict[str, dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT filename, sha256, success, applied_at "
            "FROM schema_migrations ORDER BY filename"
        )
        rows = cur.fetchall()
    return {
        r[0]: {"sha256": r[1], "success": r[2], "applied_at": r[3]} for r in rows
    }


def record_result(
    conn,
    *,
    filename: str,
    checksum: str,
    success: bool,
    duration_ms: int,
) -> None:
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


def apply_migration(conn, migration: Migration) -> bool:
    """Apply a single migration. Returns True on success, False otherwise.

    Requires the connection to already be in autocommit mode. Migration files
    manage their own BEGIN/COMMIT, and toggling autocommit here would raise
    "set_session cannot be used inside a transaction" once a cursor has
    implicitly opened one.
    """
    print(f"  -> applying {migration.filename} ...", flush=True)
    sql_text = migration.path.read_text(encoding="utf-8")
    started = time.monotonic()

    try:
        with conn.cursor() as cur:
            cur.execute(sql_text)
    except psycopg2.Error as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            record_result(
                conn,
                filename=migration.filename,
                checksum=migration.checksum,
                success=False,
                duration_ms=duration_ms,
            )
        except psycopg2.Error:
            pass
        print(f"     FAILED ({duration_ms} ms): {exc}", flush=True)
        return False

    duration_ms = int((time.monotonic() - started) * 1000)
    record_result(
        conn,
        filename=migration.filename,
        checksum=migration.checksum,
        success=True,
        duration_ms=duration_ms,
    )
    print(f"     OK ({duration_ms} ms)", flush=True)
    return True


def cmd_status(conn) -> int:
    applied = load_applied(conn)
    migrations = scan_migrations()

    print(f"Migrations directory: {MIGRATIONS_DIR}")
    print(f"Total files: {len(migrations)}  |  Recorded: {len(applied)}\n")
    print(f"{'STATUS':<10}{'FILE':<60}{'NOTE'}")
    print("-" * 100)

    pending = 0
    drifted = 0
    failed = 0
    for m in migrations:
        rec = applied.get(m.filename)
        if rec is None:
            status, note = "PENDING", ""
            pending += 1
        elif not rec["success"]:
            status, note = "FAILED", f"applied_at={rec['applied_at']} (rerun required)"
            failed += 1
        elif rec["sha256"] != m.checksum:
            status, note = "DRIFT", "file changed since apply (checksum mismatch)"
            drifted += 1
        else:
            status, note = "APPLIED", f"applied_at={rec['applied_at']}"
        print(f"{status:<10}{m.filename:<60}{note}")

    print("\nSummary:")
    print(f"  applied : {len(applied) - failed}")
    print(f"  pending : {pending}")
    print(f"  drifted : {drifted}")
    print(f"  failed  : {failed}")
    return 0 if (drifted == 0 and failed == 0) else 1


def cmd_apply_all(conn) -> int:
    applied = load_applied(conn)
    migrations = scan_migrations()

    pending = [
        m for m in migrations
        if m.filename not in applied or not applied[m.filename]["success"]
    ]
    if not pending:
        print("No pending migrations. Database is up to date.")
        return 0

    print(f"Applying {len(pending)} migration(s):")
    for m in pending:
        if not apply_migration(conn, m):
            print(f"\nABORTED at {m.filename}. Fix the error and rerun.")
            return 1
    print(f"\nAll {len(pending)} migration(s) applied successfully.")
    return 0


def cmd_apply_file(conn, raw_path: str) -> int:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / raw_path).resolve()
    if not path.is_file():
        sys.stderr.write(f"ERROR: migration file not found: {path}\n")
        return 2

    migration = Migration(path=path, filename=path.name, checksum=sha256_file(path))
    applied = load_applied(conn)
    rec = applied.get(migration.filename)
    if rec and rec["success"] and rec["sha256"] == migration.checksum:
        print(
            f"Skip: {migration.filename} already applied at {rec['applied_at']} "
            "(checksum match)."
        )
        return 0
    if rec and rec["success"] and rec["sha256"] != migration.checksum:
        sys.stderr.write(
            f"ERROR: {migration.filename} already applied with a different checksum. "
            "Refusing to re-run. Create a new migration file instead.\n"
        )
        return 1

    print(f"Applying {migration.filename}:")
    return 0 if apply_migration(conn, migration) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply Flood AI PostgreSQL migrations safely and idempotently."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--file",
        metavar="PATH",
        help="Apply a single migration file (relative to project root or absolute).",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Show which migrations are applied / pending / drifted.",
    )
    args = parser.parse_args()

    cfg = load_config()
    conn = connect(cfg)
    # Must be set BEFORE any cursor work — psycopg2 raises
    # "set_session cannot be used inside a transaction" otherwise. Migration
    # files manage their own BEGIN/COMMIT, so autocommit is the right mode.
    conn.autocommit = True
    try:
        bootstrap(conn)
        if args.status:
            return cmd_status(conn)
        if args.file:
            return cmd_apply_file(conn, args.file)
        return cmd_apply_all(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

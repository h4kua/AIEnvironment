"""
CLI entry point for the deterministic migration runner (H3).
All logic lives in db/migration_runner.py.

Usage:
    python scripts/run_migrations.py              # apply pending migrations
    python scripts/run_migrations.py --dry-run    # preview without applying
    python scripts/run_migrations.py --verify     # checksum verification only
"""

from __future__ import annotations

import argparse
import sys

from db.migration_runner import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply pending db/migrations/*.sql in deterministic lexical order."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pending migrations without applying them.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify checksums of all applied migrations; no apply.",
    )
    args = parser.parse_args()
    sys.exit(run_migrations(dry_run=args.dry_run, verify=args.verify))


if __name__ == "__main__":
    main()

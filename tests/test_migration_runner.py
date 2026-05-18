"""
Migration runner tests (H3).

All tests use mocked DB helpers and tmp_path synthetic migration files.
No live database required.

A. test_fresh_bootstrap        — nothing applied -> all files applied in order
B. test_double_replay          — all applied, checksums match -> zero applied again
C. test_checksum_drift         — stored sha256 differs -> MigrationError raised
D. test_partial_failure        — mid-run failure -> records success=FALSE, stops
E. test_gap_detection          — unapplied file precedes applied -> exit code 1
F. test_dry_run                — pending printed, apply_migration never called
G. test_verify_clean           — all applied, matching checksums -> exit 0
H. test_verify_drift           — one drift -> exit 1
I. Pure-function unit tests    — sha256_file, scan_migrations, detect_gaps
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db.migration_runner import (
    Migration,
    MigrationError,
    detect_gaps,
    run_migrations,
    scan_migrations,
    sha256_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SQL = "-- test migration\nBEGIN;\nSELECT 1;\nCOMMIT;\n"


_SQL_BYTES = _SQL.encode("utf-8")  # raw bytes — no platform newline conversion


def _make_migrations(tmp_path: Path, names: list[str]) -> list[Path]:
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_bytes(_SQL_BYTES)  # write_bytes avoids \n -> \r\n on Windows
        paths.append(p)
    return paths


def _checksum() -> str:
    return hashlib.sha256(_SQL_BYTES).hexdigest()


def _mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.autocommit = False
    conn.close = MagicMock()
    return conn


# ---------------------------------------------------------------------------
# I. Pure-function unit tests (no DB)
# ---------------------------------------------------------------------------


def test_sha256_file_deterministic(tmp_path):
    f = tmp_path / "a.sql"
    f.write_bytes(b"SELECT 1;")
    assert sha256_file(f) == sha256_file(f)
    assert sha256_file(f) == hashlib.sha256(b"SELECT 1;").hexdigest()


def test_sha256_file_different_content(tmp_path):
    a = tmp_path / "a.sql"
    b = tmp_path / "b.sql"
    a.write_bytes(b"SELECT 1;")
    b.write_bytes(b"SELECT 2;")
    assert sha256_file(a) != sha256_file(b)


def test_scan_migrations_lexical_order(tmp_path):
    _make_migrations(tmp_path, ["003_c.sql", "001_a.sql", "002_b.sql"])
    result = scan_migrations(tmp_path)
    assert [m.filename for m in result] == ["001_a.sql", "002_b.sql", "003_c.sql"]


def test_scan_migrations_empty_dir(tmp_path):
    assert scan_migrations(tmp_path) == []


def test_scan_migrations_ignores_non_sql(tmp_path):
    (tmp_path / "readme.txt").write_text("ignore me")
    (tmp_path / "001_valid.sql").write_text(_SQL)
    result = scan_migrations(tmp_path)
    assert len(result) == 1
    assert result[0].filename == "001_valid.sql"


def test_detect_gaps_none_when_all_applied(tmp_path):
    paths = _make_migrations(tmp_path, ["001.sql", "002.sql"])
    migrations = [Migration(p, p.name, _checksum()) for p in paths]
    applied = {"001.sql": {"sha256": _checksum(), "success": True},
               "002.sql": {"sha256": _checksum(), "success": True}}
    assert detect_gaps(migrations, applied) == []


def test_detect_gaps_none_when_all_pending(tmp_path):
    paths = _make_migrations(tmp_path, ["001.sql", "002.sql"])
    migrations = [Migration(p, p.name, _checksum()) for p in paths]
    assert detect_gaps(migrations, {}) == []


def test_detect_gaps_skipped_middle(tmp_path):
    paths = _make_migrations(tmp_path, ["001.sql", "002.sql", "003.sql"])
    migrations = [Migration(p, p.name, _checksum()) for p in paths]
    applied = {"001.sql": {"sha256": _checksum(), "success": True},
               "003.sql": {"sha256": _checksum(), "success": True}}
    assert detect_gaps(migrations, applied) == ["002.sql"]


def test_detect_gaps_skipped_first(tmp_path):
    paths = _make_migrations(tmp_path, ["001.sql", "002.sql"])
    migrations = [Migration(p, p.name, _checksum()) for p in paths]
    applied = {"002.sql": {"sha256": _checksum(), "success": True}}
    assert detect_gaps(migrations, applied) == ["001.sql"]


# ---------------------------------------------------------------------------
# A. Fresh bootstrap: nothing applied -> all files applied in order
# ---------------------------------------------------------------------------


def test_fresh_bootstrap_applies_all_in_order(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql", "002_b.sql", "003_c.sql"])
    conn = _mock_conn()
    applied_order: list[str] = []

    def fake_apply(conn, migration):
        applied_order.append(migration.filename)
        return 42

    with patch("db.migration_runner.get_psycopg2_connection", return_value=conn), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value={}), \
         patch("db.migration_runner.apply_migration", side_effect=fake_apply), \
         patch("db.migration_runner.record_migration") as mock_record:

        exit_code = run_migrations(migrations_dir=tmp_path)

    assert exit_code == 0
    assert applied_order == ["001_a.sql", "002_b.sql", "003_c.sql"]
    assert mock_record.call_count == 3
    for c in mock_record.call_args_list:
        assert c.args[3] is True  # success=True for all


# ---------------------------------------------------------------------------
# B. Double replay: second run applies zero migrations
# ---------------------------------------------------------------------------


def test_double_replay_applies_nothing(tmp_path):
    files = _make_migrations(tmp_path, ["001_a.sql", "002_b.sql"])
    chk = _checksum()
    already_applied = {f.name: {"sha256": chk, "success": True} for f in files}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value=already_applied), \
         patch("db.migration_runner.apply_migration") as mock_apply, \
         patch("db.migration_runner.record_migration") as mock_record:

        exit_code = run_migrations(migrations_dir=tmp_path)

    assert exit_code == 0
    mock_apply.assert_not_called()
    mock_record.assert_not_called()


# ---------------------------------------------------------------------------
# C. Checksum drift -> MigrationError
# ---------------------------------------------------------------------------


def test_checksum_drift_raises_migration_error(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql"])
    applied = {"001_a.sql": {"sha256": "a" * 64, "success": True}}  # stale

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value=applied), \
         patch("db.migration_runner.apply_migration") as mock_apply:

        with pytest.raises(MigrationError, match="Checksum drift"):
            run_migrations(migrations_dir=tmp_path)

    mock_apply.assert_not_called()


def test_checksum_drift_blocks_pending_after(tmp_path):
    """Drift on 001 must prevent 002 from being applied."""
    _make_migrations(tmp_path, ["001_a.sql", "002_b.sql"])
    applied = {"001_a.sql": {"sha256": "bad" * 21 + "b", "success": True}}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value=applied), \
         patch("db.migration_runner.apply_migration") as mock_apply:

        with pytest.raises(MigrationError):
            run_migrations(migrations_dir=tmp_path)

    mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# D. Partial failure -> records success=FALSE and stops
# ---------------------------------------------------------------------------


def test_partial_failure_records_false_and_stops(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql", "002_b.sql", "003_c.sql"])
    applied_names: list[str] = []
    recorded: list[tuple] = []

    def fake_apply(conn, migration):
        if migration.filename == "002_b.sql":
            raise Exception("FK violation")
        applied_names.append(migration.filename)
        return 10

    def fake_record(conn, filename, checksum, success, duration_ms):
        recorded.append((filename, success))

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value={}), \
         patch("db.migration_runner.apply_migration", side_effect=fake_apply), \
         patch("db.migration_runner.record_migration", side_effect=fake_record):

        with pytest.raises(MigrationError, match="002_b.sql"):
            run_migrations(migrations_dir=tmp_path)

    assert "001_a.sql" in applied_names
    assert "003_c.sql" not in applied_names

    success_map = dict(recorded)
    assert success_map.get("001_a.sql") is True
    assert success_map.get("002_b.sql") is False
    assert "003_c.sql" not in success_map


def test_previously_failed_blocks_rerun(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql"])
    chk = _checksum()
    applied = {"001_a.sql": {"sha256": chk, "success": False}}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value=applied), \
         patch("db.migration_runner.apply_migration") as mock_apply:

        with pytest.raises(MigrationError, match="success=FALSE"):
            run_migrations(migrations_dir=tmp_path)

    mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# E. Gap detection -> exit code 1
# ---------------------------------------------------------------------------


def test_gap_exits_nonzero_and_does_not_apply(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql", "002_b.sql"])
    chk = _checksum()
    applied = {"002_b.sql": {"sha256": chk, "success": True}}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.bootstrap"), \
         patch("db.migration_runner.load_applied", return_value=applied), \
         patch("db.migration_runner.apply_migration") as mock_apply:

        exit_code = run_migrations(migrations_dir=tmp_path)

    assert exit_code == 1
    mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# F. Dry-run: nothing applied, nothing recorded
# ---------------------------------------------------------------------------


def test_dry_run_does_not_apply(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql", "002_b.sql"])

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.load_applied", return_value={}), \
         patch("db.migration_runner.apply_migration") as mock_apply, \
         patch("db.migration_runner.record_migration") as mock_record:

        exit_code = run_migrations(dry_run=True, migrations_dir=tmp_path)

    assert exit_code == 0
    mock_apply.assert_not_called()
    mock_record.assert_not_called()


def test_dry_run_skips_bootstrap(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql"])

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.load_applied", return_value={}), \
         patch("db.migration_runner.bootstrap") as mock_bootstrap, \
         patch("db.migration_runner.apply_migration"), \
         patch("db.migration_runner.record_migration"):

        run_migrations(dry_run=True, migrations_dir=tmp_path)

    mock_bootstrap.assert_not_called()


# ---------------------------------------------------------------------------
# G. Verify mode: clean -> exit 0
# ---------------------------------------------------------------------------


def test_verify_clean_exits_zero(tmp_path):
    files = _make_migrations(tmp_path, ["001_a.sql", "002_b.sql"])
    chk = _checksum()
    applied = {f.name: {"sha256": chk, "success": True} for f in files}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.load_applied", return_value=applied), \
         patch("db.migration_runner.apply_migration") as mock_apply:

        exit_code = run_migrations(verify=True, migrations_dir=tmp_path)

    assert exit_code == 0
    mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# H. Verify mode: drift -> exit 1
# ---------------------------------------------------------------------------


def test_verify_drift_exits_nonzero(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql"])
    applied = {"001_a.sql": {"sha256": "0" * 64, "success": True}}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.load_applied", return_value=applied):

        exit_code = run_migrations(verify=True, migrations_dir=tmp_path)

    assert exit_code == 1


def test_verify_previously_failed_exits_nonzero(tmp_path):
    _make_migrations(tmp_path, ["001_a.sql"])
    chk = _checksum()
    applied = {"001_a.sql": {"sha256": chk, "success": False}}

    with patch("db.migration_runner.get_psycopg2_connection", return_value=_mock_conn()), \
         patch("db.migration_runner.load_applied", return_value=applied):

        exit_code = run_migrations(verify=True, migrations_dir=tmp_path)

    assert exit_code == 1

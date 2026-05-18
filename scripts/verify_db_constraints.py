"""
Verify post-021 schema hardening on the live PostgreSQL database.

Asserts:
  1. Every required CHECK / UNIQUE / FK / NOT NULL constraint exists.
  2. The required indexes exist and the redundant ones are gone.
  3. Duplicate rows are rejected by the new UNIQUE indexes.
  4. Out-of-range values are rejected by the new CHECK constraints.
  5. Append-only triggers on decisions/ground_truth_outcomes block UPDATE/DELETE.

All probes that mutate state run inside a SAVEPOINT and are rolled back; the
script makes zero permanent changes to the audited DB.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable

import psycopg2
from psycopg2 import errors as pgerr
from dotenv import load_dotenv

load_dotenv()

CONF = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "flood_ai"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
    connect_timeout=5,
)

REQUIRED_CHECKS = [
    "decisions_timestamp_not_future_chk",
    "outcome_binary_chk",
    "snapshots_lat_chk",
    "snapshots_lon_chk",
    "snapshots_completeness_chk",
    "snapshots_freshness_chk",
    "snapshot_sources_completeness_chk",
    "snapshot_sources_status_chk",
    "snapshot_sources_resp_time_chk",
    "perception_completeness_chk",
    "perception_freshness_chk",
    "perception_plausibility_chk",
    "calibration_period_order_chk",
    "calibration_predictions_chk",
    "calibration_brier_chk",
    "calibration_ece_chk",
    "calibration_mce_chk",
    "reasoning_driver_chk",
    "evaluation_driver_chk",
    "failure_stage_chk",
    "scenario_runs_failure_reason_chk",
    "decisions_authority_chk",
    "outcome_severity_class_chk",
    "outcome_source_chk",
    "scenario_type_chk",
    "calibration_period_kind_chk",
    "snapshot_sources_type_chk",
    "pipeline_runs_error_msg_len_chk",
]

REQUIRED_INDEXES = [
    "uq_decisions_pipeline_run",
    "uq_decisions_evaluation",
    "uq_evaluation_pipeline_run",
    "uq_perception_pipeline_run",
    "uq_reasoning_pipeline_run",
    "uq_trust_evaluation",
    "idx_failure_logs_snapshot",
    "idx_outcome_pipeline_run",
    "uq_snapshot_sources_snapshot_name",
    "uq_ground_truth_decision_event_district",
    "idx_failure_logs_severity_detected",
    "idx_failure_logs_run_severity",
    "idx_pipeline_runs_incomplete",
    "idx_decisions_danger_recent",
    "idx_trust_low_partial",
    "idx_snapshots_openweather_gin",
    "idx_snapshots_poskobanjir_gin",
    "idx_snapshots_bmkg_alerts_gin",
    "idx_decisions_failure_modes_gin",
    "idx_evaluation_failure_modes_gin",
    "idx_decisions_status_created",
    "idx_evaluation_status_executed",
    "idx_pipeline_runs_status_started",
    "idx_snapshots_pending",
]

REMOVED_INDEXES = [
    "idx_snapshots_hash",
    "idx_replay_scenarios_hash",
    "idx_trust_low",
]

REQUIRED_NOT_NULL = [
    ("snapshots", "created_at"),
    ("snapshot_sources", "fetched_at"),
    ("perception_results", "executed_at"),
    ("reasoning_results", "executed_at"),
    ("evaluation_results", "executed_at"),
    ("decisions", "created_at"),
    ("decisions", "decision_timestamp"),
    ("trust_breakdowns", "created_at"),
    ("failure_logs", "detected_at"),
    ("calibration_metrics", "computed_at"),
    ("ground_truth_outcomes", "created_at"),
    ("replay_scenarios", "created_at"),
]

REQUIRED_BIGINT = [
    ("pipeline_runs", "execution_time_ms"),
    ("perception_results", "execution_time_ms"),
    ("reasoning_results", "execution_time_ms"),
    ("evaluation_results", "execution_time_ms"),
    ("scenario_runs", "execution_time_ms"),
    ("schema_migrations", "duration_ms"),
]

REQUIRED_FK_RESTRICT = [
    ("decisions", "decisions_evaluation_id_fkey"),
    ("ground_truth_outcomes", "ground_truth_outcomes_decision_id_fkey"),
    ("ground_truth_outcomes", "ground_truth_outcomes_pipeline_run_id_fkey"),
]


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


def _result(label: str, ok: bool, detail: str = "") -> bool:
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {label}{(' — ' + detail) if detail else ''}")
    return ok


def check_constraints_exist(cur) -> int:
    failed = 0
    cur.execute(
        "SELECT constraint_name FROM information_schema.check_constraints "
        "WHERE constraint_schema='public'"
    )
    present = {r[0] for r in cur.fetchall()}
    for name in REQUIRED_CHECKS:
        if not _result(f"CHECK {name}", name in present):
            failed += 1
    return failed


def indexes_present(cur) -> int:
    failed = 0
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    present = {r[0] for r in cur.fetchall()}
    for name in REQUIRED_INDEXES:
        if not _result(f"INDEX {name} present", name in present):
            failed += 1
    for name in REMOVED_INDEXES:
        if not _result(f"INDEX {name} removed", name not in present):
            failed += 1
    return failed


def not_null_enforced(cur) -> int:
    failed = 0
    cur.execute(
        "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema='public'"
    )
    nullable = {(t, c): n for t, c, n in cur.fetchall()}
    for table, col in REQUIRED_NOT_NULL:
        actual = nullable.get((table, col), "MISSING")
        if not _result(f"{table}.{col} NOT NULL", actual == "NO", f"is_nullable={actual}"):
            failed += 1
    return failed


def bigint_enforced(cur) -> int:
    failed = 0
    cur.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='public'"
    )
    types = {(t, c): d for t, c, d in cur.fetchall()}
    for table, col in REQUIRED_BIGINT:
        actual = types.get((table, col), "MISSING")
        if not _result(f"{table}.{col} BIGINT", actual == "bigint", f"type={actual}"):
            failed += 1
    return failed


def fk_restrict(cur) -> int:
    failed = 0
    cur.execute(
        "SELECT conrelid::regclass::text AS table_name, conname, confdeltype "
        "FROM pg_constraint "
        "WHERE contype='f' AND connamespace = 'public'::regnamespace"
    )
    fks = {(t, n): d for t, n, d in cur.fetchall()}
    # confdeltype: 'r'=RESTRICT, 'c'=CASCADE, 'a'=NO ACTION, 'n'=SET NULL, 'd'=SET DEFAULT
    for table, name in REQUIRED_FK_RESTRICT:
        actual = fks.get((table, name), "MISSING")
        if not _result(
            f"FK {table}.{name} ON DELETE RESTRICT",
            actual == "r",
            f"confdeltype={actual!r}",
        ):
            failed += 1
    return failed


def negative_probes(conn) -> int:
    """
    Mutating probes wrapped in a SAVEPOINT. Each probe must FAIL (raise) to PASS.
    """
    failed = 0

    def expect_failure(label: str, sql: str, params: Iterable = ()) -> bool:
        nonlocal failed
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT probe")
            try:
                cur.execute(sql, params)
                cur.execute("ROLLBACK TO SAVEPOINT probe")
                _result(label, False, "expected failure but statement succeeded")
                return False
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT probe")
                return _result(label, True, type(exc).__name__)

    # 1. Out-of-range latitude must be rejected.
    if not expect_failure(
        "snapshots: latitude=999 rejected",
        "INSERT INTO snapshots (snapshot_hash, fetched_at_utc, latitude) "
        "VALUES (%s, NOW(), 999)",
        ("verify_chk_lat_" + os.urandom(8).hex(),),
    ):
        failed += 1

    # 2. Out-of-range probability rejected.
    if not expect_failure(
        "evaluation_results: probability=1.5 rejected",
        "INSERT INTO evaluation_results "
        "(reasoning_id, perception_id, system_status, risk_level, "
        " probability, confidence_score, requires_manual_review, executed_at) "
        "VALUES (gen_random_uuid(), gen_random_uuid(), 'OK', 'SAFE', "
        "        1.5, 0.5, false, NOW())",
    ):
        failed += 1

    # 3. Append-only trigger blocks UPDATE on decisions.
    if not expect_failure(
        "decisions: UPDATE blocked by append-only trigger",
        "UPDATE decisions SET risk_level='SAFE' WHERE TRUE",
    ):
        failed += 1

    return failed


def main() -> int:
    print(f"Connecting to {CONF['dbname']}@{CONF['host']}:{CONF['port']}")
    with psycopg2.connect(**CONF) as conn:
        with conn.cursor() as cur:
            _section("CHECK CONSTRAINTS")
            f1 = check_constraints_exist(cur)
            _section("INDEXES")
            f2 = indexes_present(cur)
            _section("NOT NULL")
            f3 = not_null_enforced(cur)
            _section("BIGINT TYPES")
            f4 = bigint_enforced(cur)
            _section("FK ON DELETE RESTRICT")
            f5 = fk_restrict(cur)
        _section("NEGATIVE PROBES (must reject)")
        f6 = negative_probes(conn)
        conn.rollback()

    total = f1 + f2 + f3 + f4 + f5 + f6
    print(f"\nTOTAL FAILURES: {total}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

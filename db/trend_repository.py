"""
Minimal psycopg2 repository for trend_history.

Called exclusively by app/services/trend_analysis.py.
All public functions accept an open psycopg2 connection; the caller owns
commit/rollback/close lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg2.extensions import connection as PgConnection


def insert_trend_record(
    conn: PgConnection,
    *,
    station_id: str,
    observed_at: datetime,
    probability: float,
    risk_level: str,
    water_level_ratio: float | None,
    rainfall_mm: float | None,
    max_history: int = 8,
) -> None:
    """
    Insert one prediction snapshot and prune rows beyond max_history.

    Both operations run in the same transaction so the table is always
    bounded to max_history rows per station after commit.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trend_history
                (station_id, observed_at, probability, risk_level,
                 water_level_ratio, rainfall_mm)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (station_id, observed_at) DO NOTHING
            """,
            (station_id, observed_at, probability, risk_level,
             water_level_ratio, rainfall_mm),
        )
        # Keep only the most-recent max_history rows per station.
        cur.execute(
            """
            DELETE FROM trend_history
             WHERE station_id = %s
               AND id NOT IN (
                   SELECT id
                     FROM trend_history
                    WHERE station_id = %s
                    ORDER BY observed_at DESC
                    LIMIT %s
               )
            """,
            (station_id, station_id, max_history),
        )
    conn.commit()


def get_recent_trend_records(
    conn: PgConnection,
    *,
    station_id: str,
    limit: int,
    as_of: "datetime | None" = None,
) -> list[dict[str, Any]]:
    """
    Return up to `limit` most-recent records for station_id, oldest-first.

    When ``as_of`` is provided the query is restricted to rows strictly older
    than that timestamp. This makes trend reads deterministic for a pinned
    orchestrator clock — replays with the same ``as_of`` and the same DB state
    return byte-identical rows.

    Oldest-first order matches the original deque iteration order so
    _compute_from_records() receives records in the same sequence as before.
    """
    with conn.cursor() as cur:
        if as_of is None:
            cur.execute(
                """
                SELECT observed_at, probability, risk_level,
                       water_level_ratio, rainfall_mm
                  FROM trend_history
                 WHERE station_id = %s
                 ORDER BY observed_at DESC
                 LIMIT %s
                """,
                (station_id, limit),
            )
        else:
            cur.execute(
                """
                SELECT observed_at, probability, risk_level,
                       water_level_ratio, rainfall_mm
                  FROM trend_history
                 WHERE station_id = %s
                   AND observed_at < %s
                 ORDER BY observed_at DESC
                 LIMIT %s
                """,
                (station_id, as_of, limit),
            )
        rows = cur.fetchall()

    return [
        {
            "timestamp_utc": row[0].isoformat(),
            "probability": float(row[1]),
            "risk_level": row[2],
            "water_level_ratio": float(row[3]) if row[3] is not None else None,
            "rainfall_mm": float(row[4]) if row[4] is not None else None,
        }
        for row in reversed(rows)  # oldest-first
    ]


def delete_trend_records(conn: PgConnection, *, station_id: str) -> None:
    """Delete all history for station_id. Used by reset_history() in tests."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM trend_history WHERE station_id = %s",
            (station_id,),
        )
    conn.commit()

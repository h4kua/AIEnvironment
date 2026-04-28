"""
Raw psycopg2 connection helpers for the flood_ai PostgreSQL database.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import connection as PgConnection

load_dotenv()


@dataclass(frozen=True)
class Psycopg2ConnectionConfig:
    """Connection settings loaded from environment variables."""

    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "flood_ai")
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "")
    connect_timeout: int = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
    application_name: str = os.getenv("DB_APP_NAME", "flood-ai-pipeline")


def get_psycopg2_connection(
    config: Optional[Psycopg2ConnectionConfig] = None,
) -> PgConnection:
    """
    Create a psycopg2 connection with autocommit disabled.

    The caller owns commit/rollback/close so one transaction can span the
    entire multi-stage pipeline write.
    """
    active_config = config or Psycopg2ConnectionConfig()
    connection = psycopg2.connect(
        host=active_config.host,
        port=active_config.port,
        dbname=active_config.database,
        user=active_config.user,
        password=active_config.password,
        connect_timeout=active_config.connect_timeout,
        application_name=active_config.application_name,
    )
    connection.autocommit = False
    return connection

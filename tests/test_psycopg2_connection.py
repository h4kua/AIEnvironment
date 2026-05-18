from __future__ import annotations

import pytest

from db.psycopg2_connection import Psycopg2ConnectionConfig


def test_connection_config_rejects_missing_password(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="DB_PASSWORD must be set"):
        Psycopg2ConnectionConfig(password=None)


def test_connection_config_rejects_empty_password(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="DB_PASSWORD must be set"):
        Psycopg2ConnectionConfig(password="")


def test_connection_config_rejects_whitespace_password(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="DB_PASSWORD must be set"):
        Psycopg2ConnectionConfig(password="   ")


def test_connection_config_accepts_and_trims_valid_password():
    config = Psycopg2ConnectionConfig(password="  secret  ")
    assert config.password == "secret"


def test_connection_config_preserves_explicit_zero_numeric_values():
    config = Psycopg2ConnectionConfig(password="secret", port=0, connect_timeout=0)
    assert config.port == 0
    assert config.connect_timeout == 0

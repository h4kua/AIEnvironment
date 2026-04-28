"""
Database configuration for PostgreSQL connection.

Usage:
    from db.config import get_db, init_db
    
    # Initialize connection
    init_db()
    
    # Get session
    with get_db() as session:
        session.add(snapshot)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass
class DatabaseConfig:
    """Database configuration from environment variables."""
    
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "flood_ai")
    username: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "")
    
    @property
    def url(self) -> str:
        """Build SQLAlchemy connection URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def sync_url(self) -> str:
        """Synchronous connection URL (for migrations)."""
        return f"postgresql+psycopg2://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


# Global engine and session factory
_engine = None
_SessionLocal = None


def init_db(config: DatabaseConfig | None = None) -> None:
    """
    Initialize database engine and session factory.
    
    Args:
        config: DatabaseConfig instance. If None, reads from env vars.
    """
    global _engine, _SessionLocal
    
    if config is None:
        config = DatabaseConfig()
    
    _engine = create_engine(
        config.url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
    )
    
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_engine,
    )


def get_engine():
    """Get the current database engine."""
    global _engine
    if _engine is None:
        init_db()
    return _engine


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Yields:
        SQLAlchemy Session
        
    Usage:
        with get_db() as session:
            session.add(snapshot)
            session.commit()
    """
    global _SessionLocal
    
    if _SessionLocal is None:
        init_db()
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_raw_connection():
    """Get a raw psycopg2 connection for migrations."""
    import psycopg2
    config = DatabaseConfig()
    return psycopg2.connect(
        host=config.host,
        port=config.port,
        database=config.database,
        user=config.username,
        password=config.password,
    )


# Default configuration instance
db_config = DatabaseConfig()
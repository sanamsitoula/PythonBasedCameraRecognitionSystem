"""
EVAP Alembic migration environment.
Supports async SQLAlchemy (asyncpg driver).
"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Alembic Config object ──────────────────────────────────────────────────────
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so Alembic can autogenerate migrations ──────────────────
# Each import ensures the SQLAlchemy Base.metadata is populated.
from app.db.base import Base  # noqa: F401 — registers metadata

# Phase 3 models
from app.models.camera import Camera  # noqa: F401
from app.models.alert import Alert  # noqa: F401
from app.models.person import Person  # noqa: F401
from app.models.attendance import AttendanceRecord  # noqa: F401
from app.models.employee import Employee  # noqa: F401

# Phase 4 models
from app.models.visitor import Visitor, VisitorSession  # noqa: F401
from app.models.canteen import CanteenEntry  # noqa: F401
from app.models.reid import ReIDTrack  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.zone import Zone, ZoneEvent  # noqa: F401

target_metadata = Base.metadata

# ── Read DATABASE_URL from environment (override alembic.ini) ─────────────────
def get_url() -> str:
    """Return the synchronous database URL for Alembic.

    Alembic (non-async) needs a sync driver.  We convert asyncpg → psycopg2.
    Priority: DATABASE_URL_SYNC env var > DATABASE_URL converted > alembic.ini
    """
    # 1. Explicit sync URL
    sync_url: Optional[str] = os.environ.get("DATABASE_URL_SYNC")
    if sync_url:
        return sync_url

    # 2. Convert async URL to sync
    async_url: Optional[str] = os.environ.get("DATABASE_URL")
    if async_url:
        return async_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        ).replace(
            "postgresql+aiopg://", "postgresql+psycopg2://"
        )

    # 3. Fall back to alembic.ini sqlalchemy.url (not set by default)
    return config.get_main_option("sqlalchemy.url", "")


# ── Offline migrations (generate SQL without connecting) ──────────────────────
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the SQL to the output stream.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (with async engine) ─────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync connection."""
    # Build configuration dict overriding the URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url().replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    ).replace(
        "postgresql://", "postgresql+asyncpg://"
    )

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio."""
    asyncio.run(run_async_migrations())


# ── Entry point ────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""
Alembic environment configuration.

This file runs every time you execute an alembic command.
It connects to the database and tells Alembic about your models so it can auto-detect schema changes.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

# ── This import is critical! ──
# It imports all your models so Alembic knows about them.
# Without this, `alembic revision --autogenerate` won't detect any tables.
from app.db.base import Base
import app.db.models  # noqa: F401 — imported for side effects (model registration)

# Alembic Config object (provides access to alembic.ini values)
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Tell Alembic about our models' metadata
# This is what --autogenerate compares against the live database
target_metadata = Base.metadata


def get_async_url() -> str:
    """
    Get the database URL from settings and convert it for async use.
    
    SQLAlchemy async needs 'postgresql+psycopg_async://' instead of
    'postgresql+psycopg://'. We swap the scheme here.
    """
    settings = get_settings()
    url = settings.DATABASE_URL
    # Convert sync URL to async URL
    return url.replace("postgresql+psycopg://", "postgresql+psycopg_async://")


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL without connecting to DB.
    Useful for reviewing migration SQL before applying.
    """
    url = get_async_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations against an actual database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations asynchronously.
    
    We create a temporary async engine just for migrations,
    run the migrations, then dispose of it.
    """
    engine = create_async_engine(
        get_async_url(),
        poolclass=pool.NullPool,  # Don't pool connections for migrations
    )

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """Entry point for online (connected) migrations."""
    asyncio.run(run_async_migrations())


# Alembic calls one of these based on how you invoked it
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
    
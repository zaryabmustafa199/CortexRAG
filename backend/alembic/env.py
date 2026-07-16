"""
alembic/env.py
--------------
Alembic environment configuration for async SQLAlchemy migrations.

Reads DATABASE_URL from application settings (not from alembic.ini) so that
the same .env file drives both the runtime app and migration scripts.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import settings to get the DATABASE_URL
from app.core.config import settings

# Import Base so Alembic can discover all models for autogenerate
from app.db.base import Base  # noqa: F401
from app.models.document import (  # noqa: F401
    ChunkEmbedding,
    Document,
    LeafChunk,
    ParentChunk,
    UploadJob,
)
from app.models.query import Citation, FeedbackRecord, Message, QuerySession  # noqa: F401

# Import all models to register them on Base.metadata
from app.models.user import APIKey, Profile, UsageRecord, User  # noqa: F401
from app.models.workspace import Workspace, WorkspaceMember  # noqa: F401

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

# Python logging config from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate (compares models against live DB schema)
target_metadata = Base.metadata


# ── Migration runners ─────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Emit SQL to stdout — used for generating SQL scripts without a DB."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[type-arg]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,          # detect column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

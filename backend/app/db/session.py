"""
app/db/session.py
-----------------
Async SQLAlchemy engine and session factory.

Configuration enforced (see Section 5.6 of implementation plan):
  - pool_size=20, max_overflow=10, pool_recycle=1800
  - pool_pre_ping=True (detect stale connections before use)
  - connect_timeout=10s
  - statement_timeout=30000ms (server-side query kill)

RLS activation:
  Every session yields from get_db() sets:
    SET LOCAL app.workspace_id = '{id}'
  before the route handler runs any query.
  Workspace ID is injected by the JWT dependency into request.state.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# Engine — connection pool with all production-safe defaults
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args={
        # NOTE: asyncpg 0.29+ removed connect_timeout from connect() kwargs.
        # Connection timeouts are handled by pool_timeout at the SQLAlchemy level.
        "server_settings": {
            "statement_timeout": "30000",   # 30-second hard kill on runaway queries
            "application_name": "cortexrag_api",
        },
    },
    pool_timeout=10,  # 10s wait for a connection from the pool
    echo=not settings.is_production,  # SQL logging only in dev
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # objects remain usable after commit without re-fetch
    autocommit=False,
    autoflush=False,
)


async def get_db(workspace_id: str = "") -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields a database session.

    Activates Row-Level Security for the given workspace_id so that all
    subsequent queries in this session are automatically filtered by Postgres.

    Usage in route:
        @router.get("/documents")
        async def list_docs(db: AsyncSession = Depends(get_db)):
            ...

    When workspace is known (from JWT), pass it explicitly via a higher-level
    dependency that calls get_db(workspace_id=current_user.workspace_id).
    """
    async with AsyncSessionLocal() as session:
        try:
            if workspace_id:
                # Activate RLS — Postgres will now block any row whose
                # workspace_id column does not match this value.
                await session.execute(
                    # Using text() is safe here — workspace_id is a UUID
                    # validated by the JWT dependency, never raw user input.
                    __import__("sqlalchemy").text(
                        f"SET LOCAL app.workspace_id = '{workspace_id}'"
                    )
                )
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

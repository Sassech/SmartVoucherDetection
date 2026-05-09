"""Async SQLAlchemy 2 engine, session factory and FastAPI dependency.

The engine reads `DATABASE_URL` from `config.settings` (see `config.py`),
which in turn loads `.env` from the repo root. Models will declare their
metadata against `Base` defined here, so Alembic's autogenerate can pick
them up via `target_metadata = Base.metadata` in `alembic/env.py`.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings

# Single async engine for the whole app. `pool_pre_ping` avoids stale
# connections after Postgres restarts; `future=True` is the default in 2.x
# but we set it explicitly for clarity.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

# `expire_on_commit=False` keeps loaded attributes usable after commit,
# which is what FastAPI request handlers expect when returning ORM objects.
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an `AsyncSession` per request.

    Usage in a router:

        from fastapi import Depends
        from database import get_session

        @router.get(...)
        async def handler(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with SessionLocal() as session:
        yield session

"""Smoke test for async DB connectivity (task 1.1.3).

Uses a local engine with NullPool to avoid event-loop conflicts with
conftest fixtures (see gotcha 2026-05-09 in PROGRESO.md). The global
SessionLocal from database.py reuses a pooled engine that may be bound
to a different event loop when run alongside conftest-based tests.

Skips automatically if Postgres is not reachable.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from config import settings


@pytest.mark.asyncio
async def test_select_one() -> None:
    """`SELECT 1` round-trips through a local async engine."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except (OperationalError, OSError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()

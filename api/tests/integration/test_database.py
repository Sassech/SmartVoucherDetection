"""Smoke test for the async SQLAlchemy engine (task 1.1.3).

Requires Postgres reachable on `DATABASE_URL` (see `infra/docker-compose.yml`).
Skips automatically if the DB is not available so the suite stays green in
environments without infra (CI without services, etc.).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import SessionLocal


@pytest.mark.asyncio
async def test_select_one() -> None:
    """`SELECT 1` round-trips through the async engine."""
    try:
        async with SessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except (OperationalError, OSError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")

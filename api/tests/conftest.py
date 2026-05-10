"""Fixtures compartidas de pytest para la suite de tests.

Centraliza el patron de sesion transaccional contra Postgres real +
`httpx.AsyncClient` con `get_session` override-ado. Cualquier test que
necesite DB real (history, upload E2E, futuros) usa estas fixtures.

# Por que NO reusar el engine global de `database.py`

Con `asyncio_mode=auto`, pytest-asyncio crea un event loop NUEVO por
test (scope=function por default). Las conexiones asyncpg quedan
bind-eadas al loop donde se crearon — si el pool global cachea una y
la entrega en el siguiente test, el loop original ya esta cerrado y
levanta `RuntimeError: Event loop is closed`.

Solucion: engine LOCAL por test con `poolclass=NullPool` (no reutiliza
conexiones) + `dispose()` al final.

# Por que NO `TestClient` (sync) con DB real

`fastapi.testclient.TestClient` corre el endpoint en un loop sync
efimero. Si el fixture async ya abrio una conexion asyncpg en otro
loop, mezclarla con TestClient produce `RuntimeWarning: coroutine
'Connection._cancel' was never awaited` y tests inestables.

Para tests con DB real: `httpx.AsyncClient(transport=ASGITransport(app))`.
Para tests SIN DB (mocks puros): `TestClient` sigue funcionando bien.

# Aislamiento entre tests

Cada test abre `BEGIN` sobre la conexion y hace `ROLLBACK` al final —
asi los INSERTs no contaminan la DB local entre runs. Para que el
endpoint vea los INSERTs del test, override-amos `get_session` para
que devuelva ESA misma sesion (no crear una nueva del pool).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from database import get_session
from main import app


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Sesion async transaccional contra Postgres real (rollback al final).

    Skip si Postgres no esta levantado (mantiene la suite verde en CI sin
    servicios). Engine local con `NullPool` por las razones del docstring
    del modulo.
    """
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        try:
            conn = await test_engine.connect()
        except OperationalError as exc:
            pytest.skip(f"Postgres not reachable: {exc}")

        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
            await conn.close()
    finally:
        await test_engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """`httpx.AsyncClient` con `get_session` override-ado a `db_session`.

    El endpoint usa la MISMA sesion del test → ve los INSERTs del fixture
    dentro de la transaccion. El rollback final limpia todo.
    """

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

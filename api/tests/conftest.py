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
from unittest.mock import MagicMock

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from database import get_redis, get_session
from dependencies.auth_api_key import require_api_key
from main import app
from models.seed import SYSTEM_ORG_ID, SYSTEM_USER_ID


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
        except (OperationalError, OSError) as exc:
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
async def redis_client() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Async fakeredis client — no real Redis needed in unit tests.

    Used by JWT auth tests and any test that needs Redis.
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """`httpx.AsyncClient` con `get_session` y `require_api_key` override-ados.

    - `get_session` → usa `db_session` del test (misma transaccion, rollback al final).
    - `require_api_key` → retorna un mock de Usuario con `id_usuario=SYSTEM_USER_ID`
      para que todos los tests existentes sigan pasando sin cambios.

    El rollback final limpia todo en DB.
    """
    mock_usuario = MagicMock()
    mock_usuario.id_usuario = SYSTEM_USER_ID

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_auth() -> MagicMock:
        return mock_usuario

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = _override_auth
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_api_key, None)


@pytest_asyncio.fixture
async def client_jwt(
    db_session: AsyncSession,
    redis_client: fakeredis.aioredis.FakeRedis,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """`httpx.AsyncClient` with `require_jwt` overridden (parallel to `client`).

    - `get_session` → uses `db_session` (same transaction, rollback at end).
    - `get_redis` → uses fakeredis (no real Redis needed).
    - `require_jwt` → returns a mock Usuario (admin, SYSTEM_USER_ID).

    Used by web route tests (web_comprobantes, web_stats) that need JWT auth.
    """
    from dependencies.auth_jwt import require_jwt

    mock_usuario = MagicMock()
    mock_usuario.id_usuario = SYSTEM_USER_ID
    mock_usuario.id_organizacion = SYSTEM_ORG_ID
    mock_usuario.rol = "admin"
    mock_usuario.correo = "admin@test.com"
    mock_usuario.nombre = "Test Admin"
    mock_usuario.deleted_at = None

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
        yield redis_client

    def _override_jwt() -> MagicMock:
        return mock_usuario

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_redis] = _override_redis
    app.dependency_overrides[require_jwt] = _override_jwt

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(require_jwt, None)

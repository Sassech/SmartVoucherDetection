"""TDD coverage for api/routers/history.py — RED→GREEN strict.

Covers: pagination branches (limit/offset, has_more, total, beyond total),
filters (banco, estado, fecha_desde/hasta), validation cross-checks,
and detail endpoint 404/200 with mocked DB session.

Uses httpx.ASGITransport + dependency overrides — no real Postgres.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

from database import get_session
from dependencies.auth_api_key import require_api_key
from main import app
from models.seed import SYSTEM_USER_ID

_FAKE_USER = MagicMock()
_FAKE_USER.id_usuario = SYSTEM_USER_ID


def _make_comprobante(
    *,
    estado: str = "valido",
    banco: str = "BBVA",
    referencia: str = "REF-001",
    hash_suffix: str = "aa",
) -> MagicMock:
    m = MagicMock()
    m.id_comprobante = uuid.uuid4()
    m.id_usuario = SYSTEM_USER_ID
    m.estado_actual = estado
    m.hash_documento = "a" * 62 + hash_suffix
    m.imagen_path = f"/tmp/{hash_suffix}.png"
    m.fecha_registro = datetime(2026, 1, 1, 12, 0, 0)
    m.monto = None
    m.fecha_deposito = date(2026, 1, 15)
    m.referencia = referencia
    m.numero_operacion = None
    m.banco = banco
    return m


def _fake_session_for_history(
    *,
    total: int = 0,
    items: list | None = None,
) -> AsyncMock:
    """Return AsyncMock session where first execute → count, second → items."""
    items = items or []
    mock = AsyncMock()
    # count result
    count_result = MagicMock()
    count_result.scalar_one.return_value = total
    # items result
    items_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    items_result.scalars.return_value = scalars_mock

    # side_effect chooses based on call order: first = count, second = items
    results = [count_result, items_result]

    async def _execute(_stmt):
        # pop in order; if beyond 2, keep returning items_result
        if results:
            return results.pop(0)
        return items_result

    mock.execute.side_effect = _execute
    return mock


def _detail_session(*, found: MagicMock | None) -> AsyncMock:
    mock = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = found
    mock.execute.return_value = res
    return mock


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Validation branches — no DB data needed, just 422 paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_rejects_invalid_estado_via_coverage():
    async def _override_session():
        yield _fake_session_for_history(total=0)

    def _override_auth():
        return _FAKE_USER

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = _override_auth
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history", headers={"X-API-Key": "k"}, params={"estado": "no_existe"}
        )
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_api_key, None)
    assert resp.status_code == 422
    assert "estado invalido" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_history_rejects_fecha_desde_after_fecha_hasta():
    async def _override_session():
        yield _fake_session_for_history(total=0)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history",
            headers={"X-API-Key": "k"},
            params={"fecha_desde": "2026-12-31", "fecha_hasta": "2026-01-01"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_history_rejects_limit_over_max():
    async def _override_session():
        yield _fake_session_for_history(total=0)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history", headers={"X-API-Key": "k"}, params={"limit": 999}
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_history_rejects_negative_offset():
    async def _override_session():
        yield _fake_session_for_history(total=0)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history", headers={"X-API-Key": "k"}, params={"offset": -1}
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Pagination branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_empty_returns_empty_page():
    async def _override_session():
        yield _fake_session_for_history(total=0, items=[])

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/history", headers={"X-API-Key": "k"})
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["has_more"] is False


@pytest.mark.asyncio
async def test_history_offset_beyond_total_returns_empty():
    async def _override_session():
        yield _fake_session_for_history(total=1, items=[])

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history", headers={"X-API-Key": "k"}, params={"offset": 100}
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"] == []
    assert body["has_more"] is False


@pytest.mark.asyncio
async def test_history_returns_items_and_has_more():
    c1 = _make_comprobante(referencia="A", hash_suffix="02")
    c2 = _make_comprobante(referencia="B", hash_suffix="03")

    async def _override_session():
        yield _fake_session_for_history(total=5, items=[c1, c2])

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history", headers={"X-API-Key": "k"}, params={"limit": 2, "offset": 0}
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    # also verify has_more false when offset+len == total
    async def _override_session2():
        yield _fake_session_for_history(total=2, items=[c1, c2])

    app.dependency_overrides[get_session] = _override_session2
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history", headers={"X-API-Key": "k"}, params={"limit": 2, "offset": 0}
        )
    app.dependency_overrides.clear()
    assert resp.json()["has_more"] is False


@pytest.mark.asyncio
async def test_history_with_banco_and_fecha_filters():
    comp = _make_comprobante(banco="BBVA", hash_suffix="04")

    async def _override_session():
        yield _fake_session_for_history(total=1, items=[comp])

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/history",
            headers={"X-API-Key": "k"},
            params={
                "banco": "BBVA",
                "fecha_desde": "2026-01-01",
                "fecha_hasta": "2026-02-01",
                "estado": "valido",
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_history_unauthenticated_returns_401():
    app.dependency_overrides.clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Detail endpoint: 404 and 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_comprobante_not_found_returns_404():
    async def _override_session():
        yield _detail_session(found=None)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(f"/comprobante/{uuid.uuid4()}", headers={"X-API-Key": "k"})
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_comprobante_found_returns_200():
    comp = _make_comprobante(hash_suffix="05")

    async def _override_session():
        yield _detail_session(found=comp)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = lambda: _FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/comprobante/{comp.id_comprobante}", headers={"X-API-Key": "k"}
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["id_comprobante"] == str(comp.id_comprobante)
    assert body["estado_actual"] == "valido"


@pytest.mark.asyncio
async def test_get_comprobante_unauthenticated_401():
    app.dependency_overrides.clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(f"/comprobante/{uuid.uuid4()}")
    assert resp.status_code == 401

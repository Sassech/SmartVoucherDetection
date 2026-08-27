"""TDD coverage for api/routers/validate.py.

Branches: invalid clasificacion 422, not found 404, invalid transition 409,
success valido/duplicado with Validacion creation.
Mock DB via dependency overrides — no Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

from database import get_session
from dependencies.auth_api_key import require_api_key
from main import app
from models.seed import SYSTEM_USER_ID

FAKE_USER = MagicMock()
FAKE_USER.id_usuario = SYSTEM_USER_ID


def _make_comp(*, estado: str = "en_revision", suffix: str = "aa") -> MagicMock:
    m = MagicMock()
    m.id_comprobante = uuid.uuid4()
    m.id_usuario = SYSTEM_USER_ID
    m.estado_actual = estado
    m.hash_documento = "a" * 62 + suffix
    m.imagen_path = f"/tmp/{suffix}.png"
    m.fecha_registro = datetime(2026, 1, 1, 12, 0, 0)
    m.monto = None
    m.fecha_deposito = None
    m.referencia = "REF-001"
    m.numero_operacion = None
    m.banco = "BBVA"
    return m


def _session_for_validate(*, found: MagicMock | None) -> AsyncMock:
    mock = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = found
    mock.execute.return_value = res
    mock.commit = AsyncMock()
    mock.refresh = AsyncMock()
    mock.add = MagicMock()
    return mock


@pytest.mark.asyncio
async def test_validate_invalid_clasificacion_422():
    comp = _make_comp(estado="en_revision", suffix="01")

    # clasificacion checked BEFORE DB lookup, so no DB needed
    async def _sess():
        yield _session_for_validate(found=comp)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_api_key] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{comp.id_comprobante}",
            headers={"X-API-Key": "k"},
            params={"clasificacion": "sospechoso"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_not_found_404():
    async def _sess():
        yield _session_for_validate(found=None)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_api_key] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{uuid.uuid4()}",
            headers={"X-API-Key": "k"},
            params={"clasificacion": "valido"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_not_en_revision_409():
    comp = _make_comp(estado="valido", suffix="02")  # cannot go valido→valido

    async def _sess():
        yield _session_for_validate(found=comp)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_api_key] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{comp.id_comprobante}",
            headers={"X-API-Key": "k"},
            params={"clasificacion": "valido"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_validate_success_valido():
    comp = _make_comp(estado="en_revision", suffix="03")

    async def _sess():
        yield _session_for_validate(found=comp)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_api_key] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{comp.id_comprobante}",
            headers={"X-API-Key": "k"},
            params={"clasificacion": "valido"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["estado_actual"] == "valido"


@pytest.mark.asyncio
async def test_validate_success_duplicado():
    comp = _make_comp(estado="en_revision", suffix="04")

    async def _sess():
        yield _session_for_validate(found=comp)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_api_key] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{comp.id_comprobante}",
            headers={"X-API-Key": "k"},
            params={"clasificacion": "duplicado"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["estado_actual"] == "duplicado"


@pytest.mark.asyncio
async def test_validate_unauthenticated_401():
    app.dependency_overrides.clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{uuid.uuid4()}",
            params={"clasificacion": "valido"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_validate_soft_deleted_404():
    # Simulate soft-deleted → scalar_one_or_none returns None
    async def _sess():
        yield _session_for_validate(found=None)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_api_key] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/validate/{uuid.uuid4()}",
            headers={"X-API-Key": "k"},
            params={"clasificacion": "valido"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404

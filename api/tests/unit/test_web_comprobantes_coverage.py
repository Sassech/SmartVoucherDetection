"""TDD coverage for api/routers/web_comprobantes.py.

Branches: status_filter, date_from/to, _get_comprobante_for_org 404/403,
image missing/exists with mime, decision 422/200, org-scoped list.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

from database import get_session
from dependencies.auth_jwt import require_jwt
from main import app
from models.seed import SYSTEM_ORG_ID, SYSTEM_USER_ID

FAKE_USER = MagicMock()
FAKE_USER.id_usuario = SYSTEM_USER_ID
FAKE_USER.id_organizacion = SYSTEM_ORG_ID
FAKE_USER.rol = "admin"

OTHER_ORG = uuid.uuid4()


def _make_comp(*, org_owner=SYSTEM_ORG_ID, hash_suffix="aa") -> MagicMock:
    m = MagicMock()
    m.id_comprobante = uuid.uuid4()
    m.id_usuario = SYSTEM_USER_ID
    m.imagen_path = f"/tmp/{hash_suffix}.png"
    m.referencia = "REF-001"
    m.monto = Decimal("123.45")
    m.fecha_deposito = date(2026, 1, 15)
    m.banco = "BBVA"
    m.estado_actual = "en_revision"
    m.fecha_registro = datetime(2026, 1, 15, 12, 0, 0)
    m.texto_extraido = "texto"
    m.numero_operacion = "OP-1"
    # store owner org for helper to decide 403 — not on comp itself
    m._owner_org = org_owner
    return m


def _session_for_list(*, total: int, rows: list) -> AsyncMock:
    mock = AsyncMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = total
    rows_res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    rows_res.scalars.return_value = scalars
    # first call count, second rows
    calls = [count_res, rows_res]

    async def _exec(_stmt):
        if calls:
            return calls.pop(0)
        return rows_res

    mock.execute.side_effect = _exec
    mock.flush = AsyncMock()
    mock.refresh = AsyncMock()
    mock.add = MagicMock()
    return mock


def _session_for_get_comprobante(
    *, comprobante: MagicMock | None, owner_org
) -> AsyncMock:
    """Mock for _get_comprobante_for_org: first query comp, second owner."""
    mock = AsyncMock()
    comp_res = MagicMock()
    comp_res.scalar_one_or_none.return_value = comprobante
    owner_res = MagicMock()
    owner_res.scalar_one_or_none.return_value = owner_org
    calls = [comp_res, owner_res]

    async def _exec(_stmt):
        if calls:
            return calls.pop(0)
        return owner_res

    mock.execute.side_effect = _exec
    mock.flush = AsyncMock()
    mock.refresh = AsyncMock()
    mock.add = MagicMock()
    return mock


def _session_for_decision(*, comp: MagicMock, owner_org) -> AsyncMock:
    """Decision uses _get_comprobante_for_org + validacion add."""
    mock = _session_for_get_comprobante(comprobante=comp, owner_org=owner_org)
    # keep flush/refresh/add already
    return mock


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_comprobantes_unauthenticated_401():
    app.dependency_overrides.clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/web/comprobantes/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_comprobantes_empty():
    async def _sess():
        yield _session_for_list(total=0, rows=[])

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/web/comprobantes/", headers={"Authorization": "Bearer t"})
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_comprobantes_with_status_and_date_filters():
    rows = [_make_comp(hash_suffix="01"), _make_comp(hash_suffix="02")]

    async def _sess():
        yield _session_for_list(total=2, rows=rows)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/web/comprobantes/",
            headers={"Authorization": "Bearer t"},
            params={
                "status": "valido",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "page": 1,
                "page_size": 20,
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_get_comprobante_403_foreign_org():
    comp = _make_comp(hash_suffix="03")

    async def _sess():
        yield _session_for_get_comprobante(comprobante=comp, owner_org=OTHER_ORG)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/web/comprobantes/{comp.id_comprobante}",
            headers={"Authorization": "Bearer t"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_comprobante_404_not_found():
    async def _sess():
        yield _session_for_get_comprobante(comprobante=None, owner_org=None)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/web/comprobantes/{uuid.uuid4()}", headers={"Authorization": "Bearer t"}
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_comprobante_200_same_org():
    comp = _make_comp(hash_suffix="04")

    async def _sess():
        yield _session_for_get_comprobante(comprobante=comp, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/web/comprobantes/{comp.id_comprobante}",
            headers={"Authorization": "Bearer t"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["id_comprobante"] == str(comp.id_comprobante)


@pytest.mark.asyncio
async def test_get_comprobante_image_404_missing_file():
    comp = _make_comp(hash_suffix="05")
    comp.imagen_path = "/tmp/nonexistent_sonar_test_12345.png"

    async def _sess():
        yield _session_for_get_comprobante(comprobante=comp, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/web/comprobantes/{comp.id_comprobante}/image",
            headers={"Authorization": "Bearer t"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_comprobante_image_200(tmp_path: Path):
    # create tmp file
    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG")
    comp = _make_comp(hash_suffix="06")
    comp.imagen_path = str(p)

    async def _sess():
        yield _session_for_get_comprobante(comprobante=comp, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/web/comprobantes/{comp.id_comprobante}/image",
            headers={"Authorization": "Bearer t"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    # also cover pdf mime branch
    p2 = tmp_path / "doc.pdf"
    p2.write_bytes(b"%PDF")
    comp2 = _make_comp(hash_suffix="07")
    comp2.imagen_path = str(p2)

    async def _sess2():
        yield _session_for_get_comprobante(comprobante=comp2, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess2
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            f"/web/comprobantes/{comp2.id_comprobante}/image",
            headers={"Authorization": "Bearer t"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_apply_decision_403_foreign_org():
    comp = _make_comp(hash_suffix="08")

    async def _sess():
        yield _session_for_get_comprobante(comprobante=comp, owner_org=OTHER_ORG)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/web/comprobantes/{comp.id_comprobante}/decision",
            headers={"Authorization": "Bearer t"},
            json={"accion": "aceptar"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_apply_decision_422_invalid_transition():
    comp = _make_comp(hash_suffix="09")
    comp.estado_actual = "valido"  # terminal cannot go to valido again

    async def _sess():
        yield _session_for_get_comprobante(comprobante=comp, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/web/comprobantes/{comp.id_comprobante}/decision",
            headers={"Authorization": "Bearer t"},
            json={"accion": "aceptar"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_apply_decision_success_aceptar():
    comp = _make_comp(hash_suffix="10")
    comp.estado_actual = "en_revision"

    async def _sess():
        yield _session_for_decision(comp=comp, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/web/comprobantes/{comp.id_comprobante}/decision",
            headers={"Authorization": "Bearer t"},
            json={"accion": "aceptar"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["estado_actual"] == "valido"


@pytest.mark.asyncio
async def test_apply_decision_success_rechazar():
    comp = _make_comp(hash_suffix="11")
    comp.estado_actual = "en_revision"

    async def _sess():
        yield _session_for_decision(comp=comp, owner_org=SYSTEM_ORG_ID)

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[require_jwt] = lambda: FAKE_USER
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/web/comprobantes/{comp.id_comprobante}/decision",
            headers={"Authorization": "Bearer t"},
            json={"accion": "rechazar"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["estado_actual"] == "duplicado"

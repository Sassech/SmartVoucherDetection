"""Tests for GET /web/comprobantes/, GET /web/comprobantes/{id},
and POST /web/comprobantes/{id}/decision.

Scenarios covered: S-27, S-28, S-29, S-30, S-31 (navigation — N/A backend),
S-32, S-38, S-39, S-40.

All tests use `client_jwt` fixture which overrides require_jwt with a mock
admin user belonging to SYSTEM_ORG_ID.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.comprobante import Comprobante
from models.organizacion import Organizacion
from models.seed import SYSTEM_USER_ID
from models.usuario import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_comprobante(
    id_usuario: uuid.UUID,
    estado: str = "procesando",
    fecha_deposito: date | None = date(2026, 3, 15),
    hash_suffix: str = "",
) -> Comprobante:
    return Comprobante(
        id_usuario=id_usuario,
        imagen_path=f"img/{hash_suffix or uuid.uuid4()}.jpg",
        texto_extraido=f"Texto extraido {hash_suffix}",
        referencia=f"REF-{hash_suffix or '001'}",
        monto=1000.00,
        fecha_deposito=fecha_deposito,
        numero_operacion=f"OP-{hash_suffix or '001'}",
        banco="BBVA",
        hash_documento=f"aabbccdd{hash_suffix or uuid.uuid4().hex}",
        estado_actual=estado,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def comprobante_list(db_session: AsyncSession) -> list[Comprobante]:
    """Insert 25 comprobantes belonging to SYSTEM_ORG_ID for pagination tests."""
    rows = []
    for i in range(25):
        estado = "duplicado" if i % 5 == 0 else "procesando"
        c = _make_comprobante(
            SYSTEM_USER_ID,
            estado=estado,
            fecha_deposito=date(2026, 1 if i < 10 else 3, max(1, i % 28 + 1)),
            hash_suffix=f"{i:04d}",
        )
        db_session.add(c)
        rows.append(c)
    await db_session.flush()
    return rows


@pytest_asyncio.fixture
async def single_comprobante(db_session: AsyncSession) -> Comprobante:
    """One comprobante in en_revision state, org = SYSTEM_ORG_ID."""
    c = _make_comprobante(SYSTEM_USER_ID, estado="en_revision", hash_suffix="single")
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def foreign_comprobante(db_session: AsyncSession) -> Comprobante:
    """Comprobante belonging to a different org (foreign_org_id != SYSTEM_ORG_ID)."""
    # Create a foreign org + user
    foreign_org = Organizacion(
        nombre="Foreign Org",
        plan_suscripcion="basico",
    )
    db_session.add(foreign_org)
    await db_session.flush()
    await db_session.refresh(foreign_org)

    import bcrypt
    foreign_user = Usuario(
        id_organizacion=foreign_org.id_organizacion,
        nombre="Foreign User",
        correo="foreign@test.com",
        contrasena_hash=bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode(),
        rol="operador",
    )
    db_session.add(foreign_user)
    await db_session.flush()
    await db_session.refresh(foreign_user)

    c = _make_comprobante(foreign_user.id_usuario, estado="en_revision", hash_suffix="foreign")
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)
    return c


# ---------------------------------------------------------------------------
# List endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_returns_paginated_results(
    client_jwt: AsyncClient, comprobante_list: list[Comprobante]
) -> None:
    """S-29: Pagination returns first page with correct metadata."""
    resp = await client_jwt.get("/web/comprobantes/?page=1&page_size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] == 25
    assert len(data["items"]) == 20
    assert data["has_more"] is True


@pytest.mark.asyncio
async def test_list_page_two(
    client_jwt: AsyncClient, comprobante_list: list[Comprobante]
) -> None:
    """S-29: Second page returns remaining records."""
    resp = await client_jwt.get("/web/comprobantes/?page=2&page_size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 5
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_list_status_filter_duplicado(
    client_jwt: AsyncClient, comprobante_list: list[Comprobante]
) -> None:
    """S-27: Status pill filter returns only duplicado records."""
    resp = await client_jwt.get("/web/comprobantes/?status=duplicado")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert all(item["estado_actual"] == "duplicado" for item in data["items"])


@pytest.mark.asyncio
async def test_list_date_from_filter(
    client_jwt: AsyncClient, comprobante_list: list[Comprobante]
) -> None:
    """S-28: date_from filter restricts by fecha_deposito."""
    resp = await client_jwt.get("/web/comprobantes/?date_from=2026-03-01")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        if item["fecha_deposito"] is not None:
            assert item["fecha_deposito"] >= "2026-03-01"


@pytest.mark.asyncio
async def test_list_date_to_filter(
    client_jwt: AsyncClient, comprobante_list: list[Comprobante]
) -> None:
    """S-28: date_to filter restricts by fecha_deposito (upper bound)."""
    resp = await client_jwt.get("/web/comprobantes/?date_to=2026-01-31")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        if item["fecha_deposito"] is not None:
            assert item["fecha_deposito"] <= "2026-01-31"


@pytest.mark.asyncio
async def test_list_combined_status_and_date(
    client_jwt: AsyncClient, comprobante_list: list[Comprobante]
) -> None:
    """S-32: Combined status + date_from filter applies both constraints."""
    resp = await client_jwt.get(
        "/web/comprobantes/?status=duplicado&date_from=2026-01-01"
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["estado_actual"] == "duplicado"


@pytest.mark.asyncio
async def test_list_empty_results(client_jwt: AsyncClient, db_session: AsyncSession) -> None:
    """S-30: Empty results return empty items list, not an error."""
    resp = await client_jwt.get("/web/comprobantes/?status=valido")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


# ---------------------------------------------------------------------------
# Detail endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detail_returns_full_record(
    client_jwt: AsyncClient, single_comprobante: Comprobante
) -> None:
    """S-39: Detail endpoint returns full comprobante including texto_extraido."""
    resp = await client_jwt.get(f"/web/comprobantes/{single_comprobante.id_comprobante}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id_comprobante"] == str(single_comprobante.id_comprobante)
    assert "texto_extraido" in data
    assert "imagen_path" in data
    assert "monto" in data
    assert "banco" in data
    assert "referencia" in data
    assert "fecha_deposito" in data


@pytest.mark.asyncio
async def test_detail_foreign_org_returns_403(
    client_jwt: AsyncClient, foreign_comprobante: Comprobante
) -> None:
    """S-40: Detail for comprobante belonging to different org returns 403."""
    resp = await client_jwt.get(f"/web/comprobantes/{foreign_comprobante.id_comprobante}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_detail_not_found_returns_404(client_jwt: AsyncClient) -> None:
    """Non-existent comprobante returns 404."""
    resp = await client_jwt.get(f"/web/comprobantes/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Decision endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decision_aceptar_marks_valido(
    client_jwt: AsyncClient, single_comprobante: Comprobante
) -> None:
    """R-44: POST /decision with aceptar transitions to valido."""
    resp = await client_jwt.post(
        f"/web/comprobantes/{single_comprobante.id_comprobante}/decision",
        json={"accion": "aceptar"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado_actual"] == "valido"


@pytest.mark.asyncio
async def test_decision_rechazar_marks_duplicado(
    client_jwt: AsyncClient, single_comprobante: Comprobante
) -> None:
    """R-44: POST /decision with rechazar transitions to duplicado."""
    resp = await client_jwt.post(
        f"/web/comprobantes/{single_comprobante.id_comprobante}/decision",
        json={"accion": "rechazar"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado_actual"] == "duplicado"


@pytest.mark.asyncio
async def test_decision_foreign_org_returns_403(
    client_jwt: AsyncClient, foreign_comprobante: Comprobante
) -> None:
    """S-38: Decision for foreign org comprobante returns 403 and no state change."""
    resp = await client_jwt.post(
        f"/web/comprobantes/{foreign_comprobante.id_comprobante}/decision",
        json={"accion": "aceptar"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_decision_invalid_transition_returns_422(
    client_jwt: AsyncClient, db_session: AsyncSession
) -> None:
    """Invalid state machine transition returns 422."""
    # valido is a terminal state — no transitions allowed from it.
    c = _make_comprobante(SYSTEM_USER_ID, estado="valido", hash_suffix="terminal")
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)

    resp = await client_jwt.post(
        f"/web/comprobantes/{c.id_comprobante}/decision",
        json={"accion": "aceptar"},
    )
    assert resp.status_code == 422  # HTTP_422_UNPROCESSABLE_CONTENT

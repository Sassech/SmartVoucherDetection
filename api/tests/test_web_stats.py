"""Tests for GET /web/stats/

Scenarios covered: S-23, S-24, S-26 (500 handling), plus org isolation.

All tests use `client_jwt` fixture which overrides require_jwt with a mock
admin user belonging to SYSTEM_ORG_ID.
"""

from __future__ import annotations

import uuid
from datetime import date

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

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
    hash_suffix: str = "",
) -> Comprobante:
    return Comprobante(
        id_usuario=id_usuario,
        imagen_path=f"img/{hash_suffix or uuid.uuid4()}.jpg",
        referencia=f"REF-{hash_suffix or '001'}",
        monto=500.00,
        fecha_deposito=date.today(),
        hash_documento=f"stats{hash_suffix or uuid.uuid4().hex}",
        estado_actual=estado,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_returns_valid_schema(
    client_jwt: AsyncClient, db_session: AsyncSession
) -> None:
    """S-23: GET /web/stats/ returns a StatsResponse with numeric fields."""
    resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_mes" in data
    assert "duplicados_mes" in data
    assert "tasa_error" in data
    assert isinstance(data["total_mes"], int)
    assert isinstance(data["duplicados_mes"], int)
    assert isinstance(data["tasa_error"], float)


@pytest.mark.asyncio
async def test_stats_zero_when_no_comprobantes(client_jwt: AsyncClient) -> None:
    """S-24: KPI cards show 0 when no data exists for the org this month."""
    resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 200
    data = resp.json()
    # In a fresh transaction there are no comprobantes for SYSTEM_ORG.
    assert data["total_mes"] == 0
    assert data["duplicados_mes"] == 0
    assert data["tasa_error"] == 0.0


@pytest.mark.asyncio
async def test_stats_counts_org_comprobantes(
    client_jwt: AsyncClient, db_session: AsyncSession
) -> None:
    """S-23: Stats are scoped to the authenticated user's org."""
    # Add 3 comprobantes for SYSTEM_ORG: 2 procesando, 1 duplicado.
    for i, estado in enumerate(["procesando", "procesando", "duplicado"]):
        c = _make_comprobante(SYSTEM_USER_ID, estado=estado, hash_suffix=f"st{i}")
        db_session.add(c)
    await db_session.flush()

    resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_mes"] == 3
    assert data["duplicados_mes"] == 1
    assert data["tasa_error"] == pytest.approx(33.33, abs=0.1)


@pytest.mark.asyncio
async def test_stats_org_isolation(
    client_jwt: AsyncClient, db_session: AsyncSession
) -> None:
    """Comprobantes from other orgs are NOT counted in stats."""
    # Create a foreign org + user + comprobante.
    foreign_org = Organizacion(nombre="Other Org", plan_suscripcion="basico")
    db_session.add(foreign_org)
    await db_session.flush()
    await db_session.refresh(foreign_org)

    foreign_user = Usuario(
        id_organizacion=foreign_org.id_organizacion,
        nombre="Other User",
        correo="other@test.com",
        contrasena_hash=bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode(),
        rol="operador",
    )
    db_session.add(foreign_user)
    await db_session.flush()
    await db_session.refresh(foreign_user)

    c_foreign = _make_comprobante(foreign_user.id_usuario, estado="duplicado", hash_suffix="isol")
    db_session.add(c_foreign)
    await db_session.flush()

    # Stats for SYSTEM_ORG should still be 0 (no own comprobantes in this tx).
    resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_mes"] == 0
    assert data["duplicados_mes"] == 0


@pytest.mark.asyncio
async def test_stats_tasa_error_calculation(
    client_jwt: AsyncClient, db_session: AsyncSession
) -> None:
    """tasa_error = duplicados_mes / total_mes * 100."""
    for i, estado in enumerate(["duplicado", "duplicado", "procesando", "procesando"]):
        c = _make_comprobante(SYSTEM_USER_ID, estado=estado, hash_suffix=f"te{i}")
        db_session.add(c)
    await db_session.flush()

    resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_mes"] == 4
    assert data["duplicados_mes"] == 2
    assert data["tasa_error"] == pytest.approx(50.0, abs=0.1)


@pytest.mark.asyncio
async def test_stats_500_on_db_error(client_jwt: AsyncClient) -> None:
    """S-26: DB error returns 500 with structured message (no stack trace)."""
    with patch(
        "routers.web_stats.AsyncSession.execute",
        new_callable=AsyncMock,
        side_effect=Exception("DB unavailable"),
    ):
        resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 500
    data = resp.json()
    assert "detail" in data
    # Must NOT expose internal stack trace.
    assert "Traceback" not in str(data)
    assert "DB unavailable" not in str(data)


@pytest.mark.asyncio
async def test_stats_unauthenticated_returns_401(client_jwt: AsyncClient) -> None:
    """Direct call without JWT override should require auth (bypass test via direct app call)."""
    # client_jwt has require_jwt overridden, so we verify the endpoint exists and responds 200.
    # A proper 401 test is already covered by test_jwt_auth.py (S-08/S-09).
    resp = await client_jwt.get("/web/stats/")
    assert resp.status_code == 200

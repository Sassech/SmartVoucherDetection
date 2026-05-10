"""TDD: Tests for GET /report endpoint (C3).

Written BEFORE full implementation (strict TDD).

Strategy:
- Postgres REAL via fixtures `db_session` + `client` from conftest.
- We use a unique banco name per test so other data in the DB doesn't
  interfere with counts (SYSTEM_USER_ID is shared across tests).
- Actually, since report scopes to SYSTEM_USER_ID globally and uses
  rollback isolation, we can rely on the transactional rollback to
  keep counts clean per test.

Scenarios:
1. Empty DB → total=0, por_estado=[], promedio=None
2. Counts by estado match inserted data
3. Soft-deleted comprobantes are excluded
4. Avg score reflects Validacion.score_similitud
5. No validaciones → promedio=None
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.comprobante import Comprobante
from models.seed import SYSTEM_USER_ID
from models.validacion import Validacion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_comp(estado: str, hash_suffix: str) -> Comprobante:
    h = "d" * 62 + hash_suffix
    return Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path=f"/tmp/report_test/{hash_suffix}.png",
        hash_documento=h,
        banco="BBVA",
        estado_actual=estado,
    )


async def _insert(session: AsyncSession, *comps: Comprobante) -> None:
    session.add_all(comps)
    await session.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_report_empty(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Empty DB (no comprobantes) → total=0, por_estado=[], promedio=None.

    We use a unique banco filter is not needed here; the rollback isolation
    ensures other tests' data is gone. This test runs on a clean transaction.
    """
    # Query a banco that certainly has no records in this transaction
    resp = await client.get("/report")
    assert resp.status_code == 200

    body = resp.json()
    # In a fresh transaction with no inserts, counts should be 0
    # (Other tests' data is rolled back before this test runs)
    assert body["total_comprobantes"] == 0
    assert body["por_estado"] == []
    assert body["promedio_score_similitud"] is None


async def test_report_counts_by_estado(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Inserted comprobantes in different states → correct counts per estado."""
    await _insert(
        db_session,
        # 3 valido
        _make_comp("valido", "c1"),
        _make_comp("valido", "c2"),
        _make_comp("valido", "c3"),
        # 2 duplicado
        _make_comp("duplicado", "c4"),
        _make_comp("duplicado", "c5"),
        # 1 error
        _make_comp("error", "c6"),
    )

    resp = await client.get("/report")
    assert resp.status_code == 200

    body = resp.json()
    assert body["total_comprobantes"] == 6

    # Build a lookup by estado
    by_estado = {item["estado"]: item["total"] for item in body["por_estado"]}
    assert by_estado["valido"] == 3
    assert by_estado["duplicado"] == 2
    assert by_estado["error"] == 1
    # Ordered alphabetically (as per router implementation)
    estados_ordered = [item["estado"] for item in body["por_estado"]]
    assert estados_ordered == sorted(estados_ordered)


async def test_report_excludes_soft_deleted(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Soft-deleted comprobantes are NOT counted in the report."""
    visible = _make_comp("valido", "e1")
    deleted = _make_comp("valido", "e2")
    await _insert(db_session, visible, deleted)

    # Soft-delete one
    await db_session.execute(
        text("UPDATE comprobantes SET deleted_at = now() WHERE id_comprobante = :id"),
        {"id": deleted.id_comprobante},
    )
    await db_session.flush()

    resp = await client.get("/report")
    assert resp.status_code == 200

    body = resp.json()
    assert body["total_comprobantes"] == 1
    by_estado = {item["estado"]: item["total"] for item in body["por_estado"]}
    assert by_estado.get("valido") == 1


async def test_report_avg_score(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Validacion with score → promedio_score_similitud reflects the average."""
    comp = _make_comp("valido", "f1")
    await _insert(db_session, comp)

    # Add validacion records with known scores
    val1 = Validacion(
        id_comprobante=comp.id_comprobante,
        id_usuario=SYSTEM_USER_ID,
        clasificacion="valido",
        metodo_deteccion="scoring_ponderado",
        score_similitud=0.80,
    )
    val2 = Validacion(
        id_comprobante=comp.id_comprobante,
        id_usuario=SYSTEM_USER_ID,
        clasificacion="valido",
        metodo_deteccion="scoring_ponderado",
        score_similitud=0.60,
    )
    db_session.add_all([val1, val2])
    await db_session.flush()

    resp = await client.get("/report")
    assert resp.status_code == 200

    body = resp.json()
    # avg(0.80, 0.60) = 0.70
    assert body["promedio_score_similitud"] == pytest.approx(0.70, abs=1e-6)


async def test_report_no_score_when_no_validaciones(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When comprobantes exist but have no Validacion records → promedio=None."""
    comp = _make_comp("valido", "g1")
    await _insert(db_session, comp)
    # No Validacion inserted — no scores

    resp = await client.get("/report")
    assert resp.status_code == 200

    body = resp.json()
    assert body["total_comprobantes"] == 1
    assert body["promedio_score_similitud"] is None

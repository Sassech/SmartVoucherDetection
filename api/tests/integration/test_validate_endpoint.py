"""TDD: Tests for POST /validate/{id} endpoint (CU-02).

Written BEFORE implementation (strict TDD).

Strategy:
- Postgres REAL via fixtures `db_session` + `client` from conftest.
- Test comprobantes inserted directly into the transactional session.
- All tests rollback at end — no DB pollution.

Scenarios:
1. en_revision → valido (200, estado updated, Validacion created)
2. en_revision → duplicado (200, estado updated)
3. Non-en_revision state → 409 (state machine blocks, state unchanged)
4. Invalid clasificacion → 422
5. Unknown UUID → 404
6. Soft-deleted comprobante → 404
7. Validacion record has metodo_deteccion="manual" after success
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.comprobante import Comprobante
from models.seed import SYSTEM_USER_ID
from models.validacion import Validacion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_comp(
    estado: str = "en_revision",
    hash_suffix: str = "aa",
) -> Comprobante:
    """Build a Comprobante in the given state with a unique hash."""
    h = "c" * 62 + hash_suffix
    return Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path=f"/tmp/validate_test/{hash_suffix}.png",
        hash_documento=h,
        banco="BBVA",
        estado_actual=estado,
    )


async def _insert_comp(session: AsyncSession, comp: Comprobante) -> Comprobante:
    session.add(comp)
    await session.flush()
    return comp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_validate_valido_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """en_revision → valido: returns 200 with estado_actual='valido'."""
    comp = await _insert_comp(
        db_session, _make_comp(estado="en_revision", hash_suffix="b1")
    )

    resp = await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "valido"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["estado_actual"] == "valido"
    assert body["id_comprobante"] == str(comp.id_comprobante)


async def test_validate_duplicado_success(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """en_revision → duplicado: returns 200 with estado_actual='duplicado'."""
    comp = await _insert_comp(
        db_session, _make_comp(estado="en_revision", hash_suffix="b2")
    )

    resp = await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "duplicado"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["estado_actual"] == "duplicado"


async def test_validate_not_en_revision_returns_409(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Comprobante NOT in en_revision → 409 Conflict (state machine rejects)."""
    # "sospechoso" cannot go to "valido" directly — must go through en_revision
    comp = await _insert_comp(
        db_session, _make_comp(estado="sospechoso", hash_suffix="b3")
    )

    resp = await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "valido"},
    )

    assert resp.status_code == 409
    # State must be unchanged
    await db_session.refresh(comp)
    assert comp.estado_actual == "sospechoso"


async def test_validate_invalid_clasificacion_returns_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """clasificacion outside 'valido'|'duplicado' → 422."""
    comp = await _insert_comp(
        db_session, _make_comp(estado="en_revision", hash_suffix="b4")
    )

    resp = await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "sospechoso"},
    )

    assert resp.status_code == 422


async def test_validate_not_found_returns_404(
    client: httpx.AsyncClient,
) -> None:
    """Random UUID → 404 Not Found."""
    random_id = uuid.uuid4()
    resp = await client.post(
        f"/validate/{random_id}",
        params={"clasificacion": "valido"},
    )
    assert resp.status_code == 404


async def test_validate_soft_deleted_returns_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Soft-deleted comprobante → 404 (treated as not found)."""
    comp = await _insert_comp(
        db_session, _make_comp(estado="en_revision", hash_suffix="b5")
    )

    # Soft-delete it
    await db_session.execute(
        text("UPDATE comprobantes SET deleted_at = now() WHERE id_comprobante = :id"),
        {"id": comp.id_comprobante},
    )
    await db_session.flush()

    resp = await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "valido"},
    )

    assert resp.status_code == 404


async def test_validate_creates_validacion_record(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """On success, a Validacion with metodo_deteccion='manual' is created in DB."""
    comp = await _insert_comp(
        db_session, _make_comp(estado="en_revision", hash_suffix="b6")
    )

    resp = await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "valido"},
    )

    assert resp.status_code == 200

    val_rows = (
        (
            await db_session.execute(
                select(Validacion).where(
                    Validacion.id_comprobante == comp.id_comprobante
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(val_rows) == 1
    val = val_rows[0]
    assert val.metodo_deteccion == "manual"
    assert val.clasificacion == "valido"


async def test_validate_valido_state_persisted_in_db(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After successful validation, estado_actual is persisted in the DB row."""
    comp = await _insert_comp(
        db_session, _make_comp(estado="en_revision", hash_suffix="b7")
    )

    await client.post(
        f"/validate/{comp.id_comprobante}",
        params={"clasificacion": "duplicado"},
    )

    # Reload from DB
    refreshed = (
        await db_session.execute(
            select(Comprobante).where(Comprobante.id_comprobante == comp.id_comprobante)
        )
    ).scalar_one()
    assert refreshed.estado_actual == "duplicado"

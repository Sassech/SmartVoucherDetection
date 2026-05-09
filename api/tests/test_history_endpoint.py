"""Tests del endpoint GET /history (task 1.7.3).

Estrategia: Postgres REAL del compose (no mock — el filtrado SQL es
exactamente lo que queremos validar). Cada test corre dentro de una
transaccion que se rollbackea al final, asi no contamina la DB local.

Si Postgres no esta levantado, los tests SKIPEAN (mismo patron que
`test_database.py`). Esto mantiene la suite verde en CI sin servicios.

Las fixtures `db_session` y `client` viven en `tests/conftest.py` (1.8.1).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.comprobante import Comprobante
from models.seed import SYSTEM_USER_ID


def _make_comp(
    *,
    banco: str = "BBVA",
    estado: str = "valido",
    fecha_dep: date | None = None,
    hash_suffix: str = "00",
    referencia: str | None = "REF-001",
) -> Comprobante:
    """Construye un Comprobante con defaults razonables.

    `hash_suffix` permite generar hashes unicos sin coordinar entre tests.
    SHA-256 es 64 hex chars; relleno con 'a' los primeros 62 + 2 del suffix.

    NO seteamos `id_comprobante` — dejamos que el modelo use su `default=uuid7`,
    que genera UUIDs ordenables por tiempo. Esto importa para tests de
    ordering: dentro de una misma transaccion `func.now()` devuelve el mismo
    timestamp, y el tiebreaker del endpoint es `id_comprobante DESC`.
    """
    h = ("a" * 62) + hash_suffix
    return Comprobante(
        id_usuario=SYSTEM_USER_ID,
        imagen_path=f"/tmp/test/{hash_suffix}.png",
        hash_documento=h,
        banco=banco,
        estado_actual=estado,
        fecha_deposito=fecha_dep,
        referencia=referencia,
    )


async def _insert(session: AsyncSession, *comps: Comprobante) -> None:
    """Inserta y flush-ea (no commit — la transaccion se rollbackea)."""
    session.add_all(comps)
    await session.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_history_empty_returns_empty_page(client, db_session):
    # Filtramos por un banco que NO insertamos para garantizar set vacio,
    # sin asumir que la DB de dev este limpia.
    response = await client.get(
        "/history", params={"banco": "BANCO_INEXISTENTE_ZZZ"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["has_more"] is False


async def test_history_returns_inserted_comprobantes(client, db_session):
    banco = "TESTBANCO_LIST"
    await _insert(
        db_session,
        _make_comp(banco=banco, hash_suffix="01", referencia="REF-A"),
        _make_comp(banco=banco, hash_suffix="02", referencia="REF-B"),
        _make_comp(banco=banco, hash_suffix="03", referencia="REF-C"),
    )

    response = await client.get("/history", params={"banco": banco})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    refs = {item["campos_extraidos"]["referencia"] for item in body["items"]}
    assert refs == {"REF-A", "REF-B", "REF-C"}
    assert all(item["campos_extraidos"]["banco"] == banco for item in body["items"])


async def test_history_pagination_limit_and_offset(client, db_session):
    banco = "TESTBANCO_PAG"
    await _insert(
        db_session,
        *[_make_comp(banco=banco, hash_suffix=f"{i:02d}") for i in range(10, 15)],
    )

    p1 = (
        await client.get(
            "/history", params={"banco": banco, "limit": 2, "offset": 0}
        )
    ).json()
    assert p1["total"] == 5
    assert len(p1["items"]) == 2
    assert p1["has_more"] is True

    p2 = (
        await client.get(
            "/history", params={"banco": banco, "limit": 2, "offset": 2}
        )
    ).json()
    assert len(p2["items"]) == 2
    assert p2["has_more"] is True

    p3 = (
        await client.get(
            "/history", params={"banco": banco, "limit": 2, "offset": 4}
        )
    ).json()
    assert len(p3["items"]) == 1
    assert p3["has_more"] is False

    ids_all = (
        [i["id_comprobante"] for i in p1["items"]]
        + [i["id_comprobante"] for i in p2["items"]]
        + [i["id_comprobante"] for i in p3["items"]]
    )
    assert len(set(ids_all)) == 5


async def test_history_offset_beyond_total_returns_empty(client, db_session):
    banco = "TESTBANCO_OFFSET"
    await _insert(db_session, _make_comp(banco=banco, hash_suffix="20"))

    body = (
        await client.get("/history", params={"banco": banco, "offset": 100})
    ).json()

    assert body["total"] == 1
    assert body["items"] == []
    assert body["has_more"] is False


async def test_history_filter_by_estado(client, db_session):
    banco = "TESTBANCO_EST"
    await _insert(
        db_session,
        _make_comp(banco=banco, hash_suffix="30", estado="valido"),
        _make_comp(banco=banco, hash_suffix="31", estado="duplicado"),
        _make_comp(banco=banco, hash_suffix="32", estado="duplicado"),
    )

    body = (
        await client.get(
            "/history", params={"banco": banco, "estado": "duplicado"}
        )
    ).json()

    assert body["total"] == 2
    assert all(i["estado_actual"] == "duplicado" for i in body["items"])


async def test_history_filter_by_fecha_range(client, db_session):
    banco = "TESTBANCO_FECHA"
    await _insert(
        db_session,
        _make_comp(banco=banco, hash_suffix="40", fecha_dep=date(2026, 1, 15)),
        _make_comp(banco=banco, hash_suffix="41", fecha_dep=date(2026, 2, 15)),
        _make_comp(banco=banco, hash_suffix="42", fecha_dep=date(2026, 3, 15)),
        _make_comp(banco=banco, hash_suffix="43", fecha_dep=None),  # sin fecha
    )

    body = (
        await client.get(
            "/history",
            params={
                "banco": banco,
                "fecha_desde": "2026-02-01",
                "fecha_hasta": "2026-02-28",
            },
        )
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["campos_extraidos"]["fecha"] == "2026-02-15"


async def test_history_orders_by_fecha_registro_desc(client, db_session):
    """El item mas reciente debe aparecer primero."""
    banco = "TESTBANCO_ORDEN"
    # Inserts secuenciales en orden A, B, C → fecha_registro asciende A<B<C.
    # El response debe venir C, B, A.
    a = _make_comp(banco=banco, hash_suffix="50", referencia="REF-A")
    await _insert(db_session, a)
    b = _make_comp(banco=banco, hash_suffix="51", referencia="REF-B")
    await _insert(db_session, b)
    c = _make_comp(banco=banco, hash_suffix="52", referencia="REF-C")
    await _insert(db_session, c)

    body = (await client.get("/history", params={"banco": banco})).json()

    refs = [i["campos_extraidos"]["referencia"] for i in body["items"]]
    assert refs == ["REF-C", "REF-B", "REF-A"]


async def test_history_excludes_soft_deleted(client, db_session):
    banco = "TESTBANCO_SOFTDEL"
    visible = _make_comp(banco=banco, hash_suffix="60", referencia="VIVO")
    deleted = _make_comp(banco=banco, hash_suffix="61", referencia="MUERTO")
    await _insert(db_session, visible, deleted)

    await db_session.execute(
        text(
            "UPDATE comprobantes SET deleted_at = now() "
            "WHERE id_comprobante = :id"
        ),
        {"id": deleted.id_comprobante},
    )
    await db_session.flush()

    body = (await client.get("/history", params={"banco": banco})).json()

    assert body["total"] == 1
    assert body["items"][0]["campos_extraidos"]["referencia"] == "VIVO"


async def test_history_only_returns_system_user(client, db_session):
    """El endpoint hardcodea SYSTEM_USER_ID — verificamos que los items
    devueltos coincidan con ese id_usuario."""
    banco = "TESTBANCO_TENANT"
    await _insert(
        db_session, _make_comp(banco=banco, hash_suffix="70", referencia="MIO")
    )

    body = (await client.get("/history", params={"banco": banco})).json()

    assert body["total"] == 1
    assert all(
        item["id_usuario"] == str(SYSTEM_USER_ID) for item in body["items"]
    )


# ---------------------------------------------------------------------------
# Validacion de query params (no requieren DB con datos)
# ---------------------------------------------------------------------------


async def test_history_rejects_invalid_estado(client):
    response = await client.get("/history", params={"estado": "no_existe"})
    assert response.status_code == 422
    assert "estado invalido" in response.json()["detail"].lower()


async def test_history_rejects_fecha_desde_after_fecha_hasta(client):
    response = await client.get(
        "/history",
        params={"fecha_desde": "2026-12-31", "fecha_hasta": "2026-01-01"},
    )
    assert response.status_code == 422


async def test_history_rejects_limit_over_max(client):
    response = await client.get("/history", params={"limit": 999})
    assert response.status_code == 422  # FastAPI lo valida con `le=100`


async def test_history_rejects_negative_offset(client):
    response = await client.get("/history", params={"offset": -1})
    assert response.status_code == 422

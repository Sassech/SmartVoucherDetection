"""Tests para api/models/configuracion_sistema.py.

Estrategia:
- Unit: verifica que el modelo tiene los atributos de columna correctos.
- Integration: usa conftest `db_session` — inserta fila, la consulta, verifica
  que updated_at existe. NO verifica el trigger de onupdate porque depende de
  que Postgres ejecute el BEFORE UPDATE trigger (no hay soporte SQLAlchemy sin
  DB-level trigger). Verifica insercion y lectura.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.configuracion_sistema import ConfiguracionSistema


# ---------------------------------------------------------------------------
# Unit tests — atributos del modelo (sin DB)
# ---------------------------------------------------------------------------


def test_model_has_key_column():
    """El modelo tiene columna `key` como primary key."""
    mapper = inspect(ConfiguracionSistema)
    cols = {c.key: c for c in mapper.columns}
    assert "key" in cols
    col = cols["key"]
    assert col.primary_key


def test_model_has_value_column():
    """El modelo tiene columna `value` NOT NULL."""
    mapper = inspect(ConfiguracionSistema)
    cols = {c.key: c for c in mapper.columns}
    assert "value" in cols
    col = cols["value"]
    assert not col.nullable


def test_model_has_updated_at_column():
    """El modelo tiene columna `updated_at` con server_default."""
    mapper = inspect(ConfiguracionSistema)
    cols = {c.key: c for c in mapper.columns}
    assert "updated_at" in cols
    col = cols["updated_at"]
    assert col.server_default is not None


def test_model_tablename():
    """El modelo usa el nombre de tabla correcto."""
    assert ConfiguracionSistema.__tablename__ == "configuracion_sistema"


def test_model_has_no_deleted_at_column():
    """ConfiguracionSistema NO tiene SoftDeleteMixin (sin deleted_at)."""
    mapper = inspect(ConfiguracionSistema)
    col_names = {c.key for c in mapper.columns}
    assert "deleted_at" not in col_names


# ---------------------------------------------------------------------------
# Integration tests — requieren Postgres via conftest `db_session`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_query_row(db_session: AsyncSession):
    """Insertar una fila y consultarla devuelve los valores correctos."""
    row = ConfiguracionSistema(key="test.integration.key", value="42.0")
    db_session.add(row)
    await db_session.flush()

    result = await db_session.execute(
        select(ConfiguracionSistema).where(
            ConfiguracionSistema.key == "test.integration.key"
        )
    )
    fetched = result.scalar_one()
    assert fetched.key == "test.integration.key"
    assert fetched.value == "42.0"
    assert fetched.updated_at is not None


@pytest.mark.asyncio
async def test_updated_at_set_on_insert(db_session: AsyncSession):
    """updated_at se popula automaticamente en el INSERT (server_default=now())."""
    row = ConfiguracionSistema(key="test.updated_at.insert", value="hello")
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)

    assert row.updated_at is not None


@pytest.mark.asyncio
async def test_primary_key_is_varchar(db_session: AsyncSession):
    """La clave primaria es un string (VARCHAR), no UUID."""
    row = ConfiguracionSistema(key="test.varchar.pk", value="somevalue")
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)

    assert isinstance(row.key, str)
    assert row.key == "test.varchar.pk"


@pytest.mark.asyncio
async def test_seeded_scoring_weights_exist(db_session: AsyncSession):
    """Los 4 pesos de scoring sembrados en la migracion existen en la DB."""
    expected_keys = ["scoring.w_ref", "scoring.w_text", "scoring.w_monto", "scoring.w_fecha"]
    result = await db_session.execute(
        select(ConfiguracionSistema).where(
            ConfiguracionSistema.key.in_(expected_keys)
        )
    )
    rows = result.scalars().all()
    found_keys = {r.key for r in rows}
    assert found_keys == set(expected_keys)


@pytest.mark.asyncio
async def test_seeded_weights_values(db_session: AsyncSession):
    """Los valores sembrados en la migracion coinciden con los defaults esperados."""
    result = await db_session.execute(
        select(ConfiguracionSistema).where(
            ConfiguracionSistema.key.in_(
                ["scoring.w_ref", "scoring.w_text", "scoring.w_monto", "scoring.w_fecha"]
            )
        )
    )
    rows = {r.key: r.value for r in result.scalars().all()}
    assert rows.get("scoring.w_ref") == "0.35"
    assert rows.get("scoring.w_text") == "0.30"
    assert rows.get("scoring.w_monto") == "0.20"
    assert rows.get("scoring.w_fecha") == "0.15"

"""Tests para api/services/config_service.py.

Estrategia:
- Unit: mock AsyncSession para verificar logica de construccion de ScoringWeights,
  fallback a DEFAULTS, y comportamiento del cache (segunda llamada no ejecuta DB).
- Integration: AsyncSession real via conftest — verifica que la DB sembrada
  por la migracion carga los pesos correctamente.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import services.config_service as config_module
from services.config_service import (
    DEFAULTS,
    get_scoring_weights,
    invalidate_weights_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_with_rows(rows: list[tuple[str, str]]) -> AsyncMock:
    """Crea un mock de AsyncSession que retorna `rows` como (key, value) tuples."""
    mock_rows = [MagicMock(key=k, value=v) for k, v in rows]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_rows
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ---------------------------------------------------------------------------
# Unit tests (mock session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_scoring_weights_all_rows_builds_correct_dataclass():
    """Con las 4 filas correctas se construye ScoringWeights con los valores correctos."""
    invalidate_weights_cache()
    session = _make_session_with_rows([
        ("scoring.w_ref", "0.35"),
        ("scoring.w_text", "0.30"),
        ("scoring.w_monto", "0.20"),
        ("scoring.w_fecha", "0.15"),
    ])

    weights = await get_scoring_weights(session)

    assert weights.w_ref == pytest.approx(0.35)
    assert weights.w_text == pytest.approx(0.30)
    assert weights.w_monto == pytest.approx(0.20)
    assert weights.w_fecha == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_get_scoring_weights_missing_keys_fall_back_to_defaults():
    """Con solo 2 filas, las keys ausentes usan los valores de DEFAULTS."""
    invalidate_weights_cache()
    session = _make_session_with_rows([
        ("scoring.w_ref", "0.50"),   # custom
        ("scoring.w_text", "0.50"),  # custom — nota: no suman 1 en test, OK
    ])

    weights = await get_scoring_weights(session)

    assert weights.w_ref == pytest.approx(0.50)
    assert weights.w_text == pytest.approx(0.50)
    # Las ausentes usan valores de DEFAULTS
    assert weights.w_monto == pytest.approx(DEFAULTS.w_monto)
    assert weights.w_fecha == pytest.approx(DEFAULTS.w_fecha)


@pytest.mark.asyncio
async def test_get_scoring_weights_cache_hit_skips_db_call():
    """Segunda llamada con cache poblado NO ejecuta session.execute."""
    invalidate_weights_cache()

    session1 = _make_session_with_rows([
        ("scoring.w_ref", "0.35"),
        ("scoring.w_text", "0.30"),
        ("scoring.w_monto", "0.20"),
        ("scoring.w_fecha", "0.15"),
    ])
    session2 = AsyncMock(spec=AsyncSession)
    session2.execute = AsyncMock()

    # Primera llamada — pobla el cache
    await get_scoring_weights(session1)
    # Segunda llamada — debe usar el cache
    weights2 = await get_scoring_weights(session2)

    session2.execute.assert_not_called()
    assert weights2.w_ref == pytest.approx(0.35)


@pytest.mark.asyncio
async def test_invalidate_weights_cache_forces_reload():
    """Despues de invalidate_weights_cache(), la siguiente llamada consulta la DB."""
    invalidate_weights_cache()
    session1 = _make_session_with_rows([
        ("scoring.w_ref", "0.35"),
        ("scoring.w_text", "0.30"),
        ("scoring.w_monto", "0.20"),
        ("scoring.w_fecha", "0.15"),
    ])
    await get_scoring_weights(session1)

    # Invalidar
    invalidate_weights_cache()

    session2 = _make_session_with_rows([
        ("scoring.w_ref", "0.40"),
        ("scoring.w_text", "0.30"),
        ("scoring.w_monto", "0.20"),
        ("scoring.w_fecha", "0.10"),
    ])
    weights_reloaded = await get_scoring_weights(session2)

    session2.execute.assert_called_once()
    assert weights_reloaded.w_ref == pytest.approx(0.40)


@pytest.mark.asyncio
async def test_empty_db_uses_all_defaults():
    """Sin filas en DB, todos los campos usan DEFAULTS."""
    invalidate_weights_cache()
    session = _make_session_with_rows([])

    weights = await get_scoring_weights(session)

    assert weights.w_ref == pytest.approx(DEFAULTS.w_ref)
    assert weights.w_text == pytest.approx(DEFAULTS.w_text)
    assert weights.w_monto == pytest.approx(DEFAULTS.w_monto)
    assert weights.w_fecha == pytest.approx(DEFAULTS.w_fecha)


def test_defaults_sum_to_one():
    """Los DEFAULTS suman 1.0 (invariante de negocio)."""
    total = DEFAULTS.w_ref + DEFAULTS.w_text + DEFAULTS.w_monto + DEFAULTS.w_fecha
    assert total == pytest.approx(1.0, abs=0.001)


def test_invalidate_weights_cache_sets_none():
    """invalidate_weights_cache pone _weights_cache a None."""
    invalidate_weights_cache()
    assert config_module._weights_cache is None


# ---------------------------------------------------------------------------
# Integration test — DB real via conftest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_loads_weights_from_seeded_db(db_session: AsyncSession):
    """get_scoring_weights lee los pesos sembrados por la migracion."""
    invalidate_weights_cache()

    weights = await get_scoring_weights(db_session)

    # Los valores sembrados en la migracion son los DEFAULTS
    assert weights.w_ref == pytest.approx(0.35)
    assert weights.w_text == pytest.approx(0.30)
    assert weights.w_monto == pytest.approx(0.20)
    assert weights.w_fecha == pytest.approx(0.15)

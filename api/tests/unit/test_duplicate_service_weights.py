"""Tests para la integracion de config_service en duplicate_service (6.A.3).

Verifica que compute_score() acepta un session opcional y:
- Si session != None: usa los pesos de get_scoring_weights(session).
- Si session == None: usa los pesos modulo-nivel (backward compat).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.config_service import ScoringWeights, invalidate_weights_cache
from services.duplicate_service import W_FECHA, W_MONTO, W_REF, W_TEXT, compute_score


def _make_comp(
    *,
    referencia: str | None = "TRF-001",
    monto: Decimal | None = Decimal("1500.00"),
    fecha_deposito: date | None = date(2026, 5, 1),
    texto_extraido: str | None = "texto comprobante deposito",
) -> SimpleNamespace:
    return SimpleNamespace(
        id_comprobante=uuid.uuid4(),
        id_usuario=uuid.uuid4(),
        referencia=referencia,
        monto=monto,
        fecha_deposito=fecha_deposito,
        texto_extraido=texto_extraido,
        deleted_at=None,
        imagen_path="/tmp/fake.png",
        hash_documento="aa" * 32,
        numero_operacion=None,
        banco=None,
    )


# ---------------------------------------------------------------------------
# Tests con session=None (backward compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_score_session_none_uses_module_constants():
    """Con session=None, compute_score usa W_REF/W_TEXT/W_MONTO/W_FECHA."""
    nuevo = _make_comp(referencia="TRF-001")
    existente = _make_comp(referencia="TRF-001", monto=Decimal("1500.00"))

    # Sin session — debe ser un coroutine (async) o sync
    # compute_score es async cuando recibe session, pero si session=None
    # debe seguir funcionando (retorna float directamente o como coroutine).
    result = await compute_score(nuevo, existente, session=None)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


@pytest.mark.asyncio
async def test_compute_score_session_none_same_as_old_behavior():
    """Con session=None, el score es identico al calculo con W_* modulo."""
    from services.duplicate_service import _s_fecha, _s_monto, _s_ref, _s_texto

    nuevo = _make_comp()
    existente = _make_comp(referencia="TRF-001", monto=Decimal("1500.00"))

    expected = (
        W_REF * _s_ref(nuevo.referencia, existente.referencia)
        + W_TEXT * _s_texto(nuevo.texto_extraido, existente.texto_extraido)
        + W_MONTO * _s_monto(nuevo.monto, existente.monto)
        + W_FECHA * _s_fecha(nuevo.fecha_deposito, existente.fecha_deposito)
    )

    result = await compute_score(nuevo, existente, session=None)
    assert result == pytest.approx(expected, abs=0.001)


# ---------------------------------------------------------------------------
# Tests con mock session (custom weights)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_score_with_session_uses_db_weights():
    """Con session provisto, compute_score usa los pesos de get_scoring_weights."""
    invalidate_weights_cache()

    custom_weights = ScoringWeights(w_ref=0.50, w_text=0.20, w_monto=0.20, w_fecha=0.10)

    nuevo = _make_comp(referencia="TRF-001", texto_extraido=None)
    existente = _make_comp(referencia="TRF-001", texto_extraido=None)

    with patch(
        "services.duplicate_service.get_scoring_weights",
        new=AsyncMock(return_value=custom_weights),
    ) as mock_get:
        session = AsyncMock()
        result = await compute_score(nuevo, existente, session=session)
        mock_get.assert_called_once_with(session)

    # Con referencia identica y texto None, score = w_ref*1 + w_text*0 + w_monto*1 + w_fecha*1
    # = 0.50 + 0 + 0.20 + 0.10 = 0.80
    assert result == pytest.approx(0.80, abs=0.01)


@pytest.mark.asyncio
async def test_compute_score_custom_weights_change_result():
    """Los pesos personalizados cambian el resultado respecto a los defaults."""
    invalidate_weights_cache()

    # Pesos que enfatizan el monto (no los defaults 0.35/0.30/0.20/0.15)
    heavy_monto = ScoringWeights(w_ref=0.10, w_text=0.10, w_monto=0.70, w_fecha=0.10)

    nuevo = _make_comp(referencia="TRF-ABC", monto=Decimal("1000.00"), texto_extraido=None)
    existente = _make_comp(referencia="TRF-XYZ", monto=Decimal("1000.00"), texto_extraido=None)

    with patch(
        "services.duplicate_service.get_scoring_weights",
        new=AsyncMock(return_value=heavy_monto),
    ):
        session = AsyncMock()
        result_custom = await compute_score(nuevo, existente, session=session)

    # Con defaults — referencia diferente pero monto igual
    result_default = await compute_score(nuevo, existente, session=None)

    # Con pesos default: w_ref*bajo + 0 + w_monto*1 + w_fecha*1 = 0.35*low + 0.20 + 0.15
    # Con heavy_monto: w_ref*bajo + 0 + 0.70*1 + w_fecha*1 = 0.10*low + 0.70 + 0.10
    # El custom debe dar score mayor (monto tiene peso 0.70)
    assert result_custom > result_default

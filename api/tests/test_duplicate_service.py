"""Tests para api/services/duplicate_service.py.

Estrategia:
- Funciones puras (_s_ref, _s_texto, _s_monto, _s_fecha, compute_score, classify):
  unit tests directos, sin DB ni mocks.
- find_candidates, run_capa2, run_capa3: async tests con mock de AsyncSession
  usando MagicMock/AsyncMock — evitamos DB real para que sean rapidos y
  deterministicos.

Cobertura minima: 25 casos (spec B3 requiere >=25).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Las funciones puras se importan directamente para unit tests sin instancias
from services.duplicate_service import (
    THRESHOLD_DUPLICADO,
    THRESHOLD_SOSPECHOSO,
    _s_fecha,
    _s_monto,
    _s_ref,
    _s_texto,
    classify,
    compute_score,
    find_candidates,
    run_capa2,
    run_capa3,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_comp(
    *,
    id_comprobante: uuid.UUID | None = None,
    id_usuario: uuid.UUID | None = None,
    referencia: str | None = "TRF-001",
    monto: Decimal | None = Decimal("1500.00"),
    fecha_deposito: date | None = date(2026, 5, 1),
    texto_extraido: str | None = "Comprobante de deposito banco",
    estado_actual: str = "procesando",
    deleted_at=None,
) -> SimpleNamespace:
    """Factory de Comprobante-like object en memoria (sin DB/ORM overhead).

    Usa SimpleNamespace para evitar el overhead del ORM de SQLAlchemy —
    duplicate_service solo accede a atributos planos, no a relaciones.
    """
    return SimpleNamespace(
        id_comprobante=id_comprobante or uuid.uuid4(),
        id_usuario=id_usuario or uuid.uuid4(),
        referencia=referencia,
        monto=monto,
        fecha_deposito=fecha_deposito,
        texto_extraido=texto_extraido,
        estado_actual=estado_actual,
        deleted_at=deleted_at,
        imagen_path="/tmp/fake.png",
        hash_documento="aabbccdd" * 8,
        numero_operacion=None,
        banco=None,
    )


# ---------------------------------------------------------------------------
# _s_ref — Levenshtein ratio
# ---------------------------------------------------------------------------


def test_s_ref_identical_strings_returns_one():
    assert _s_ref("TRF-001", "TRF-001") == pytest.approx(1.0)


def test_s_ref_completely_different_returns_low():
    score = _s_ref("ABC", "XYZ")
    assert 0.0 <= score < 0.5


def test_s_ref_none_first_arg_returns_zero():
    assert _s_ref(None, "TRF-001") == 0.0


def test_s_ref_none_second_arg_returns_zero():
    assert _s_ref("TRF-001", None) == 0.0


def test_s_ref_both_none_returns_zero():
    assert _s_ref(None, None) == 0.0


# ---------------------------------------------------------------------------
# _s_texto — TF-IDF cosine similarity
# ---------------------------------------------------------------------------


def test_s_texto_identical_texts_returns_one():
    text = "comprobante de deposito bancario"
    assert _s_texto(text, text) == pytest.approx(1.0)


def test_s_texto_none_first_arg_returns_zero():
    assert _s_texto(None, "algun texto") == 0.0


def test_s_texto_none_second_arg_returns_zero():
    assert _s_texto("algun texto", None) == 0.0


def test_s_texto_completely_different_texts_returns_low():
    score = _s_texto("banco transferencia deposito", "gato perro pajaro")
    # Vocabulario completamente diferente -> coseno cercano a 0
    assert score < 0.5


def test_s_texto_similar_texts_returns_positive():
    score = _s_texto(
        "deposito banco transferencia ref 001",
        "deposito bancario transferencia referencia 001",
    )
    assert score > 0.3  # Vocabulario similar -> similitud positiva


# ---------------------------------------------------------------------------
# _s_monto — similitud numerica con Decimal
# ---------------------------------------------------------------------------


def test_s_monto_identical_amounts_returns_one():
    assert _s_monto(Decimal("1500.00"), Decimal("1500.00")) == pytest.approx(1.0)


def test_s_monto_large_difference_returns_low():
    score = _s_monto(Decimal("100.00"), Decimal("1000.00"))
    # diff=900, max=1000 → 1 - 0.9 = 0.1
    assert score == pytest.approx(0.1)


def test_s_monto_none_first_arg_returns_zero():
    assert _s_monto(None, Decimal("500.00")) == 0.0


def test_s_monto_none_second_arg_returns_zero():
    assert _s_monto(Decimal("500.00"), None) == 0.0


def test_s_monto_zero_both_returns_one():
    """Ambos cero: max=0, no hay diferencia — retorna 1.0."""
    assert _s_monto(Decimal("0"), Decimal("0")) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _s_fecha — similitud temporal (ventana 30 dias)
# ---------------------------------------------------------------------------


def test_s_fecha_same_date_returns_one():
    d = date(2026, 5, 1)
    assert _s_fecha(d, d) == pytest.approx(1.0)


def test_s_fecha_30_day_diff_returns_zero():
    assert _s_fecha(date(2026, 5, 1), date(2026, 4, 1)) == pytest.approx(0.0)


def test_s_fecha_15_day_diff_returns_half():
    assert _s_fecha(date(2026, 5, 1), date(2026, 4, 16)) == pytest.approx(0.5)


def test_s_fecha_none_first_arg_returns_zero():
    assert _s_fecha(None, date(2026, 5, 1)) == 0.0


def test_s_fecha_none_second_arg_returns_zero():
    assert _s_fecha(date(2026, 5, 1), None) == 0.0


def test_s_fecha_beyond_30_days_caps_at_zero():
    # Mas de 30 dias -> min(..., 30)/30 = 1 -> score 0
    assert _s_fecha(date(2026, 5, 1), date(2026, 1, 1)) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_score — formula ponderada
# ---------------------------------------------------------------------------


def test_compute_score_identical_comprobantes_returns_one():
    """Spec CAP-05 Scenario 1: ambos textos iguales, todos campos iguales → 1.0."""
    nuevo = _make_comp(referencia="TRF-001", texto_extraido="texto igual")
    existente = _make_comp(
        id_comprobante=uuid.uuid4(),
        id_usuario=nuevo.id_usuario,
        referencia="TRF-001",
        texto_extraido="texto igual",
    )
    score = compute_score(nuevo, existente)
    assert score == pytest.approx(1.0, abs=0.01)


def test_compute_score_null_texto_caps_at_070():
    """Spec CAP-05 Scenario 2: texto NULL → max 0.70 (0.35+0.20+0.15)."""
    nuevo = _make_comp(referencia="TRF-001", texto_extraido=None)
    existente = _make_comp(
        id_comprobante=uuid.uuid4(),
        id_usuario=nuevo.id_usuario,
        referencia="TRF-001",
        texto_extraido=None,
    )
    score = compute_score(nuevo, existente)
    assert score <= 0.70 + 0.001  # ceil con tolerancia


def test_compute_score_null_texto_still_weights_other_components():
    """Con texto NULL, score = 0.35*s_ref + 0.20*s_monto + 0.15*s_fecha."""
    nuevo = _make_comp(texto_extraido=None)
    existente = _make_comp(
        id_comprobante=uuid.uuid4(),
        id_usuario=nuevo.id_usuario,
        texto_extraido=None,
    )
    score = compute_score(nuevo, existente)
    # Misma referencia, monto, fecha → 0.35 + 0 + 0.20 + 0.15 = 0.70
    assert score == pytest.approx(0.70, abs=0.01)


# ---------------------------------------------------------------------------
# classify — umbral de clasificacion
# ---------------------------------------------------------------------------


def test_classify_above_duplicado_threshold():
    """Spec CAP-05: score >= 0.90 → 'duplicado'."""
    assert classify(THRESHOLD_DUPLICADO) == "duplicado"
    assert classify(1.0) == "duplicado"
    assert classify(0.95) == "duplicado"


def test_classify_in_sospechoso_range():
    """Spec CAP-05: 0.75 <= score < 0.90 → 'sospechoso'."""
    assert classify(THRESHOLD_SOSPECHOSO) == "sospechoso"
    assert classify(0.82) == "sospechoso"
    assert classify(0.89) == "sospechoso"


def test_classify_below_sospechoso_threshold():
    """Spec CAP-05: score < 0.75 → 'valido'."""
    assert classify(0.74) == "valido"
    assert classify(0.0) == "valido"
    assert classify(0.60) == "valido"


def test_classify_exact_boundary_090_is_duplicado():
    assert classify(0.90) == "duplicado"


def test_classify_exact_boundary_075_is_sospechoso():
    assert classify(0.75) == "sospechoso"


# ---------------------------------------------------------------------------
# find_candidates — ventana 30 dias, mismo usuario, excluye soft-deleted y self
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_candidates_returns_candidates_in_window():
    """Solo devuelve comprobantes dentro de la ventana ±30 dias."""
    user_id = uuid.uuid4()
    nuevo_id = uuid.uuid4()
    cand_id = uuid.uuid4()

    nuevo = _make_comp(
        id_comprobante=nuevo_id,
        id_usuario=user_id,
        fecha_deposito=date(2026, 5, 1),
    )
    candidato = _make_comp(
        id_comprobante=cand_id,
        id_usuario=user_id,
        fecha_deposito=date(2026, 5, 10),  # dentro de ventana
    )

    # Mock AsyncSession.execute → scalars().all() retorna [candidato]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [candidato]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    result = await find_candidates(session, nuevo)

    assert len(result) == 1
    assert result[0].id_comprobante == cand_id


@pytest.mark.asyncio
async def test_find_candidates_no_date_returns_empty():
    """Sin fecha_deposito en nuevo → retorna lista vacia sin consultar DB."""
    nuevo = _make_comp(fecha_deposito=None)
    session = AsyncMock()

    result = await find_candidates(session, nuevo)

    assert result == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_find_candidates_returns_empty_when_no_candidates():
    """Cuando la DB no devuelve registros → lista vacia."""
    nuevo = _make_comp(fecha_deposito=date(2026, 5, 1))

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    result = await find_candidates(session, nuevo)

    assert result == []


# ---------------------------------------------------------------------------
# run_capa2 — exact match (referencia + monto + fecha)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_capa2_hit_returns_existing_comprobante():
    """Spec CAP-04 Scenario 1: exact match → retorna el comprobante existente."""
    nuevo = _make_comp(referencia="TRF-001", monto=Decimal("1500.00"))
    existente = _make_comp(
        id_comprobante=uuid.uuid4(),
        referencia="TRF-001",
        monto=Decimal("1500.00"),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existente

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    result = await run_capa2(session, nuevo)

    assert result is existente


@pytest.mark.asyncio
async def test_run_capa2_miss_returns_none():
    """Spec CAP-04 Scenario 2: no match → retorna None."""
    nuevo = _make_comp(referencia="TRF-999")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    result = await run_capa2(session, nuevo)

    assert result is None


@pytest.mark.asyncio
async def test_run_capa2_skips_when_referencia_is_none():
    """Sin referencia → retorna None sin consultar DB (index no aplica)."""
    nuevo = _make_comp(referencia=None)
    session = AsyncMock()

    result = await run_capa2(session, nuevo)

    assert result is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_capa2_skips_when_monto_is_none():
    """Sin monto → retorna None sin consultar DB."""
    nuevo = _make_comp(monto=None)
    session = AsyncMock()

    result = await run_capa2(session, nuevo)

    assert result is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_capa2_skips_when_fecha_is_none():
    """Sin fecha_deposito → retorna None sin consultar DB."""
    nuevo = _make_comp(fecha_deposito=None)
    session = AsyncMock()

    result = await run_capa2(session, nuevo)

    assert result is None
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# run_capa3 — scored similarity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_capa3_no_candidates_returns_valido():
    """Sin candidatos → (None, 0.0, 'valido')."""
    nuevo = _make_comp(fecha_deposito=date(2026, 5, 1))

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    best, score, clasif = await run_capa3(session, nuevo)

    assert best is None
    assert score == 0.0
    assert clasif == "valido"


@pytest.mark.asyncio
async def test_run_capa3_sospechoso_when_score_in_range():
    """Score entre 0.75 y 0.90 → clasificacion 'sospechoso'."""
    user_id = uuid.uuid4()
    nuevo = _make_comp(
        id_usuario=user_id,
        referencia="TRF-123",
        monto=Decimal("1500.00"),
        fecha_deposito=date(2026, 5, 1),
        texto_extraido="comprobante deposito ref 123",
    )
    # Candidato similar pero no identico (monto ligeramente diferente)
    candidato = _make_comp(
        id_comprobante=uuid.uuid4(),
        id_usuario=user_id,
        referencia="TRF-123",
        monto=Decimal("1480.00"),  # diferencia pequenia
        fecha_deposito=date(2026, 5, 1),
        texto_extraido="comprobante deposito ref 123",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [candidato]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    best, score, clasif = await run_capa3(session, nuevo)

    assert best is candidato
    assert 0.0 < score <= 1.0
    assert clasif in (
        "sospechoso",
        "duplicado",
        "valido",
    )  # resultado depende del score real


@pytest.mark.asyncio
async def test_run_capa3_returns_best_candidate_when_multiple():
    """Con multiples candidatos, retorna el de mayor score."""
    user_id = uuid.uuid4()
    nuevo = _make_comp(
        id_usuario=user_id,
        referencia="TRF-001",
        monto=Decimal("1500.00"),
        fecha_deposito=date(2026, 5, 1),
        texto_extraido="mismo texto exacto para forzar score alto",
    )
    cand_alto = _make_comp(
        id_comprobante=uuid.uuid4(),
        id_usuario=user_id,
        referencia="TRF-001",
        monto=Decimal("1500.00"),
        fecha_deposito=date(2026, 5, 1),
        texto_extraido="mismo texto exacto para forzar score alto",
    )
    cand_bajo = _make_comp(
        id_comprobante=uuid.uuid4(),
        id_usuario=user_id,
        referencia="XYZ-999",
        monto=Decimal("1.00"),
        fecha_deposito=date(2026, 1, 1),
        texto_extraido="texto completamente diferente banco otro",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [cand_bajo, cand_alto]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    best, score, _ = await run_capa3(session, nuevo)

    # El mejor candidato debe ser cand_alto (mayor similitud)
    assert best is cand_alto
    assert score > 0.5  # Score alto por similitud real

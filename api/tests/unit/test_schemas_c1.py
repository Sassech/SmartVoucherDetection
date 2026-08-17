"""TDD RED: Tests for new schemas C1 — ValidacionResponse and ReportResponse.

Written BEFORE implementation (strict TDD).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# ValidacionResponse
# ---------------------------------------------------------------------------


def test_validacion_response_instantiates_with_all_fields():
    """ValidacionResponse can be created with all required + optional fields."""
    from schemas.validacion import ValidacionResponse

    now = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    id_v = uuid.uuid4()
    id_c = uuid.uuid4()
    id_orig = uuid.uuid4()

    obj = ValidacionResponse(
        id_validacion=id_v,
        id_comprobante=id_c,
        id_comprobante_original=id_orig,
        clasificacion="valido",
        metodo_deteccion="manual",
        score_similitud=0.85,
        fecha_validacion=now,
    )

    assert obj.id_validacion == id_v
    assert obj.id_comprobante == id_c
    assert obj.id_comprobante_original == id_orig
    assert obj.clasificacion == "valido"
    assert obj.metodo_deteccion == "manual"
    assert obj.score_similitud == pytest.approx(0.85)
    assert obj.fecha_validacion == now


def test_validacion_response_with_null_optional_fields():
    """ValidacionResponse accepts None for nullable fields."""
    from schemas.validacion import ValidacionResponse

    now = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)

    obj = ValidacionResponse(
        id_validacion=uuid.uuid4(),
        id_comprobante=uuid.uuid4(),
        id_comprobante_original=None,
        clasificacion="duplicado",
        metodo_deteccion="campos_exactos",
        score_similitud=None,
        fecha_validacion=now,
    )

    assert obj.id_comprobante_original is None
    assert obj.score_similitud is None
    assert obj.clasificacion == "duplicado"


# ---------------------------------------------------------------------------
# ReportResponse + EstadoCount
# ---------------------------------------------------------------------------


def test_report_response_instantiates_with_all_fields():
    """ReportResponse can be created with real data."""
    from schemas.report import EstadoCount, ReportResponse

    counts = [
        EstadoCount(estado="valido", total=15),
        EstadoCount(estado="duplicado", total=3),
    ]

    obj = ReportResponse(
        total_comprobantes=18,
        por_estado=counts,
        promedio_score_similitud=0.72,
    )

    assert obj.total_comprobantes == 18
    assert len(obj.por_estado) == 2
    assert obj.por_estado[0].estado == "valido"
    assert obj.por_estado[0].total == 15
    assert obj.promedio_score_similitud == pytest.approx(0.72)


def test_report_response_with_null_promedio():
    """ReportResponse accepts None for promedio_score_similitud."""
    from schemas.report import ReportResponse

    obj = ReportResponse(
        total_comprobantes=0,
        por_estado=[],
        promedio_score_similitud=None,
    )

    assert obj.total_comprobantes == 0
    assert obj.por_estado == []
    assert obj.promedio_score_similitud is None


def test_estado_count_fields():
    """EstadoCount exposes estado and total."""
    from schemas.report import EstadoCount

    ec = EstadoCount(estado="sospechoso", total=5)
    assert ec.estado == "sospechoso"
    assert ec.total == 5

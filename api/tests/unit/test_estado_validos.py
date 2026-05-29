"""Tests para ESTADOS_VALIDOS — A0.1 (TDD RED → GREEN).

Verifica que todos los 8 estados del diagrama de estados Fase 2 estén
presentes en la tupla ESTADOS_VALIDOS y en el schema ComprobanteCreate.
"""

from __future__ import annotations

import pytest


def test_sospechoso_in_estados_validos() -> None:
    """A0.1: 'sospechoso' debe estar en ESTADOS_VALIDOS (estaba ausente)."""
    from models.comprobante import ESTADOS_VALIDOS

    assert "sospechoso" in ESTADOS_VALIDOS


def test_estados_validos_has_all_eight_states() -> None:
    """Todos los 8 estados del FSM deben existir en la tupla."""
    from models.comprobante import ESTADOS_VALIDOS

    expected = {
        "recibido",
        "procesando",
        "comparando",
        "sospechoso",
        "en_revision",
        "valido",
        "duplicado",
        "error",
    }
    assert expected == set(ESTADOS_VALIDOS)


def test_comprobante_create_accepts_sospechoso_estado() -> None:
    """ComprobanteCreate debe aceptar 'sospechoso' como estado_actual válido."""
    import uuid

    from pydantic import ValidationError

    from schemas.comprobante import CamposExtraidos, ComprobanteCreate

    campos = CamposExtraidos(banco="BBVA")
    try:
        obj = ComprobanteCreate(
            id_usuario=uuid.uuid4(),
            imagen_path="/tmp/test.png",
            hash_documento="a" * 64,
            campos=campos,
            estado_actual="sospechoso",
        )
        assert obj.estado_actual == "sospechoso"
    except ValidationError as exc:
        pytest.fail(f"ComprobanteCreate rejected 'sospechoso': {exc}")


def test_comprobante_response_accepts_sospechoso_estado() -> None:
    """ComprobanteResponse debe aceptar 'sospechoso' como estado_actual válido."""
    import uuid
    from datetime import datetime, timezone

    from pydantic import ValidationError

    from schemas.comprobante import CamposExtraidos, ComprobanteResponse

    campos = CamposExtraidos(banco="BBVA")
    try:
        obj = ComprobanteResponse(
            id_comprobante=uuid.uuid4(),
            id_usuario=uuid.uuid4(),
            estado_actual="sospechoso",
            hash_documento="b" * 64,
            imagen_path="/tmp/test.png",
            fecha_registro=datetime.now(timezone.utc),
            campos_extraidos=campos,
        )
        assert obj.estado_actual == "sospechoso"
    except ValidationError as exc:
        pytest.fail(f"ComprobanteResponse rejected 'sospechoso': {exc}")

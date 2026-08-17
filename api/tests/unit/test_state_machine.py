"""Tests para api/services/state_machine.py — A2 (Strict TDD).

Cubre:
- Todos los bordes validos del FSM (10 transiciones del spec CAP-02 +
  2 bordes defensivos de error segun design prompt).
- Transiciones invalidas: estados terminales, pares incorrectos, self-loops.
- InvalidTransitionError: atributos from_state / to_state.
- apply_transition: muta el objeto ORM en-lugar, no hace I/O.

Sin DB, sin mocks — pure Python.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeComp(NamedTuple):
    """Minimo objeto que simula un ORM Comprobante para apply_transition.

    NamedTuple es inmutable — no sirve para el test de mutacion. Usamos
    una simple clase con __slots__ en cambio.
    """

    estado_actual: str


class _MutableComp:
    """Simula ORM Comprobante — solo el campo estado_actual."""

    __slots__ = ("estado_actual",)

    def __init__(self, estado: str) -> None:
        self.estado_actual = estado


# ---------------------------------------------------------------------------
# A2 — Tests RED (antes de que exista state_machine.py)
# ---------------------------------------------------------------------------


# ── 1. Importacion del modulo (falla si el modulo no existe) ─────────────


def test_state_machine_module_importable() -> None:
    """El modulo debe existir e importar sin error."""
    from services import state_machine  # noqa: F401


def test_transitions_dict_is_exported() -> None:
    """TRANSITIONS debe ser un dict exportado del modulo."""
    from services.state_machine import TRANSITIONS

    assert isinstance(TRANSITIONS, dict)
    assert len(TRANSITIONS) > 0


# ── 2. Transiciones VALIDAS — parametricas ───────────────────────────────

VALID_TRANSITIONS = [
    # (from_state, to_state, description)
    ("recibido", "procesando", "upload start"),
    ("recibido", "error", "upload error defensive"),
    ("procesando", "comparando", "OCR success"),
    ("procesando", "error", "OCR failure"),
    ("comparando", "valido", "score < 0.75"),
    ("comparando", "sospechoso", "0.75 <= score < 0.90"),
    ("comparando", "duplicado", "hash/exact/score >= 0.90"),
    ("comparando", "error", "scoring failure"),
    ("sospechoso", "en_revision", "auto-advance"),
    ("en_revision", "valido", "manual confirm"),
    ("en_revision", "duplicado", "manual reject"),
    ("en_revision", "error", "en_revision error defensive"),
    ("error", "recibido", "retry"),
]


@pytest.mark.parametrize("from_state,to_state,desc", VALID_TRANSITIONS)
def test_validate_transition_allows_valid_edge(
    from_state: str, to_state: str, desc: str
) -> None:
    """validate_transition no levanta para bordes validos del FSM."""
    from services.state_machine import validate_transition

    # No debe levantar ninguna excepcion.
    validate_transition(from_state, to_state)


@pytest.mark.parametrize("from_state,to_state,desc", VALID_TRANSITIONS)
def test_apply_transition_mutates_estado_on_valid_edge(
    from_state: str, to_state: str, desc: str
) -> None:
    """apply_transition cambia estado_actual en-lugar para bordes validos."""
    from services.state_machine import apply_transition

    comp = _MutableComp(from_state)
    apply_transition(comp, to_state)
    assert comp.estado_actual == to_state


# ── 3. Transiciones INVALIDAS ────────────────────────────────────────────

INVALID_TRANSITIONS = [
    # (from_state, to_state, reason)
    # Self-loops — ninguno permitido
    ("recibido", "recibido", "self-loop recibido"),
    ("procesando", "procesando", "self-loop procesando"),
    ("comparando", "comparando", "self-loop comparando"),
    ("sospechoso", "sospechoso", "self-loop sospechoso"),
    ("en_revision", "en_revision", "self-loop en_revision"),
    ("valido", "valido", "self-loop valido terminal"),
    ("duplicado", "duplicado", "self-loop duplicado terminal"),
    ("error", "error", "self-loop error terminal"),
    # Estados terminales — no tienen bordes salientes
    ("valido", "procesando", "from terminal valido"),
    ("valido", "recibido", "from terminal valido 2"),
    ("duplicado", "recibido", "from terminal duplicado"),
    ("duplicado", "valido", "from terminal duplicado 2"),
    # Pares incorrectos (salto invalido)
    ("recibido", "comparando", "skip procesando"),
    ("recibido", "valido", "skip all"),
    ("procesando", "valido", "skip comparando"),
    ("procesando", "sospechoso", "skip comparando for sospechoso"),
    ("comparando", "recibido", "backward"),
    ("comparando", "procesando", "backward"),
    ("sospechoso", "valido", "skip en_revision"),
    ("sospechoso", "duplicado", "skip en_revision"),
    ("en_revision", "sospechoso", "backward"),
    ("en_revision", "comparando", "backward"),
    ("error", "valido", "invalid from error"),
    ("error", "comparando", "invalid from error 2"),
]


@pytest.mark.parametrize("from_state,to_state,reason", INVALID_TRANSITIONS)
def test_validate_transition_raises_for_invalid_edge(
    from_state: str, to_state: str, reason: str
) -> None:
    """validate_transition levanta InvalidTransitionError para bordes invalidos."""
    from services.state_machine import InvalidTransitionError, validate_transition

    with pytest.raises(InvalidTransitionError):
        validate_transition(from_state, to_state)


@pytest.mark.parametrize("from_state,to_state,reason", INVALID_TRANSITIONS)
def test_apply_transition_raises_and_does_not_mutate_on_invalid_edge(
    from_state: str, to_state: str, reason: str
) -> None:
    """apply_transition levanta y NO muta estado cuando la transicion es invalida."""
    from services.state_machine import InvalidTransitionError, apply_transition

    comp = _MutableComp(from_state)
    with pytest.raises(InvalidTransitionError):
        apply_transition(comp, to_state)
    # Estado NO debe haber cambiado.
    assert comp.estado_actual == from_state


# ── 4. InvalidTransitionError — atributos ────────────────────────────────


def test_invalid_transition_error_has_from_state_attribute() -> None:
    """InvalidTransitionError debe exponer .from_state con el estado origen."""
    from services.state_machine import InvalidTransitionError, validate_transition

    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition("valido", "procesando")

    assert exc_info.value.from_state == "valido"


def test_invalid_transition_error_has_to_state_attribute() -> None:
    """InvalidTransitionError debe exponer .to_state con el estado destino."""
    from services.state_machine import InvalidTransitionError, validate_transition

    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition("valido", "procesando")

    assert exc_info.value.to_state == "procesando"


def test_invalid_transition_error_message_contains_states() -> None:
    """El mensaje de InvalidTransitionError debe contener ambos estados."""
    from services.state_machine import InvalidTransitionError, validate_transition

    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition("duplicado", "recibido")

    msg = str(exc_info.value)
    assert "duplicado" in msg
    assert "recibido" in msg


# ── 5. Propiedades del FSM ────────────────────────────────────────────────


def test_terminal_states_have_no_outgoing_transitions() -> None:
    """valido y duplicado son terminales — sin bordes salientes."""
    from services.state_machine import TRANSITIONS

    assert TRANSITIONS.get("valido", set()) == set()
    assert TRANSITIONS.get("duplicado", set()) == set()


def test_sospechoso_only_transitions_to_en_revision() -> None:
    """sospechoso solo puede avanzar a en_revision (auto-advance)."""
    from services.state_machine import TRANSITIONS

    assert TRANSITIONS["sospechoso"] == {"en_revision"}


def test_apply_transition_no_io_is_pure() -> None:
    """apply_transition no debe hacer I/O — solo muta estado del objeto."""
    from services.state_machine import apply_transition

    # Si no hay efectos secundarios, llamar N veces no falla.
    comp = _MutableComp("recibido")
    apply_transition(comp, "procesando")
    assert comp.estado_actual == "procesando"

    # Aplicar otro borde valido desde el nuevo estado.
    apply_transition(comp, "comparando")
    assert comp.estado_actual == "comparando"


def test_validate_transition_does_not_mutate_any_object() -> None:
    """validate_transition es una funcion pura — no recibe ni muta objetos."""
    from services.state_machine import validate_transition

    # Solo toma strings — no hay objeto que mutar. Verificamos que retorna None.
    result = validate_transition("recibido", "procesando")
    assert result is None

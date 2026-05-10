"""State machine for Comprobante.estado_actual transitions.

Valid transitions (from → allowed_targets):
  recibido    → {procesando, error}
  procesando  → {comparando, error}
  comparando  → {valido, sospechoso, duplicado, en_revision, error}
  en_revision → {valido, duplicado, error}
  valido      → set()           # terminal
  sospechoso  → {en_revision}   # human review queues it
  duplicado   → set()           # terminal
  error       → {recibido}      # allow retry

Nota sobre diseño:
- Spec CAP-02 define 10 transiciones de negocio.
- Se agregan bordes defensivos de 'error' desde recibido y en_revision
  para cubrir fallos inesperados en cualquier etapa del pipeline.
- 'error' no es terminal: permite reintentos via error → recibido.
- No hay I/O en este modulo — opera solo sobre el estado en memoria.
  El caller es responsable del commit a la DB.
"""

from __future__ import annotations

TRANSITIONS: dict[str, set[str]] = {
    "recibido": {"procesando", "error"},
    "procesando": {"comparando", "error"},
    "comparando": {"valido", "sospechoso", "duplicado", "en_revision", "error"},
    "en_revision": {"valido", "duplicado", "error"},
    "sospechoso": {"en_revision"},
    "valido": set(),
    "duplicado": set(),
    "error": {"recibido"},
}


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid transition: {from_state!r} \u2192 {to_state!r}")


def validate_transition(from_state: str, to_state: str) -> None:
    """Raise InvalidTransitionError if the transition is not allowed.

    Pure function — no side effects, no I/O.
    """
    allowed = TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise InvalidTransitionError(from_state, to_state)


def apply_transition(comprobante: object, to_state: str) -> None:
    """Validate and apply a state transition to a Comprobante ORM instance (in-place).

    Does NOT flush/commit — caller manages the session.

    Args:
        comprobante: Any object with a mutable `estado_actual` str attribute.
        to_state: Target state string.

    Raises:
        InvalidTransitionError: If the transition is not allowed.
    """
    validate_transition(comprobante.estado_actual, to_state)  # type: ignore[attr-defined]
    comprobante.estado_actual = to_state  # type: ignore[attr-defined]

"""Servicio de configuracion del sistema con cache lazy de pesos de scoring.

Patron de diseno (D-15 — Weight loading — module-level lazy singleton):
- `_weights_cache` es None hasta la primera llamada a `get_scoring_weights()`.
- La primera llamada SELECT la DB, construye ScoringWeights y guarda en cache.
- Las llamadas siguientes devuelven el cache sin tocar la DB.
- `invalidate_weights_cache()` pone el cache a None — lo llama el endpoint
  de admin POST /admin/config/reload, o los tests que necesitan reiniciar.

Fallback: si una key no esta en la DB (tabla vacia o key faltante), se usa
el valor de DEFAULTS para esa key. Esto garantiza backward compat incluso
si la migracion de datos no corrio.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.configuracion_sistema import ConfiguracionSistema


@dataclass
class ScoringWeights:
    """Pesos de scoring para la deteccion de duplicados Capa 3.

    Los cuatro pesos deben sumar 1.0. Definidos en `configuracion_sistema`
    bajo las keys `scoring.w_*`.
    """

    w_ref: float = 0.35
    w_text: float = 0.30
    w_monto: float = 0.20
    w_fecha: float = 0.15


# Valores por defecto — usados cuando la DB no tiene la key correspondiente.
DEFAULTS = ScoringWeights()

# Cache modular lazy — None hasta la primera llamada.
_weights_cache: ScoringWeights | None = None

# Mapeo de key DB → atributo del dataclass
_KEY_TO_ATTR: dict[str, str] = {
    "scoring.w_ref": "w_ref",
    "scoring.w_text": "w_text",
    "scoring.w_monto": "w_monto",
    "scoring.w_fecha": "w_fecha",
}


async def get_scoring_weights(session: AsyncSession) -> ScoringWeights:
    """Devuelve los pesos de scoring desde el cache o la DB.

    Cache hit:  retorna inmediatamente sin tocar la DB.
    Cache miss: SELECT las 4 filas de `configuracion_sistema`, construye
                `ScoringWeights`, almacena en cache y retorna.
    Fallback:   si una key no existe en la DB, usa el valor de DEFAULTS.
    """
    global _weights_cache

    if _weights_cache is not None:
        return _weights_cache

    result = await session.execute(
        select(ConfiguracionSistema).where(
            ConfiguracionSistema.key.in_(list(_KEY_TO_ATTR.keys()))
        )
    )
    rows = result.scalars().all()

    # Construir dict {key: float_value} desde las filas de DB
    db_values: dict[str, float] = {}
    for row in rows:
        if row.key in _KEY_TO_ATTR:
            try:
                db_values[row.key] = float(row.value)
            except (ValueError, TypeError):
                # Si el valor no es un float valido, usar DEFAULTS
                pass

    # Construir ScoringWeights con fallback a DEFAULTS para keys ausentes
    weights = ScoringWeights(
        w_ref=db_values.get("scoring.w_ref", DEFAULTS.w_ref),
        w_text=db_values.get("scoring.w_text", DEFAULTS.w_text),
        w_monto=db_values.get("scoring.w_monto", DEFAULTS.w_monto),
        w_fecha=db_values.get("scoring.w_fecha", DEFAULTS.w_fecha),
    )

    _weights_cache = weights
    return _weights_cache


def invalidate_weights_cache() -> None:
    """Invalida el cache de pesos — la proxima llamada recargara desde la DB.

    Llamar desde:
    - Tests que necesiten un cache limpio entre tests.
    - Endpoint admin POST /admin/config/reload despues de actualizar weights.
    - Restart de proceso (el cache se reinicia automaticamente al ser None).
    """
    global _weights_cache
    _weights_cache = None

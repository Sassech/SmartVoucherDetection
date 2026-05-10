"""Cliente Redis async — wrapper minimo sobre redis.asyncio.

Responsabilidad en Fase 1: exponer `ping()` para el endpoint de health.
Fase 2 (B1): agrega `check_hash` y `set_hash` para Capa 1 de deteccion
de duplicados.

Decisiones de diseno:
- **Pool global lazy**: el cliente se crea la primera vez que se usa y se
  cachea en `_client`. Asi evitamos abrir/cerrar conexion por request (cara)
  y no instanciamos Redis al importar el modulo (lo que rompe tests que no
  necesitan Redis).
- **`ping()` NO levanta**: el endpoint health NO debe romper si Redis esta
  caido — el HTTP debe seguir respondiendo 200 con `redis.ok=False`. Esa
  es justamente la senial que el load balancer/dashboard espera ver.
- **Timeout explicito**: si Redis tarda mas que `timeout_s` devolvemos
  `False`. Sin esto, una red lenta podria bloquear al endpoint health
  por el `socket_timeout` del cliente (que es mucho mas grande).
- **`from_url(decode_responses=False)`**: el default de redis-py decodifica
  a str, lo que rompe valores binarios. En Fase 2.1.1 vamos a manejar
  hashes como str pero los bytes-puros pueden venir despues — mejor
  decidir en cada caller que esperar.
- **`check_hash` / `set_hash` nunca levantan**: mismo patron que `ping()` —
  infraestructura caida no interrumpe el pipeline; Capa 2 actua como fallback.
"""

from __future__ import annotations

import asyncio
import logging
import uuid as _uuid

import redis.asyncio as redis_async
from redis.asyncio import Redis
from redis.exceptions import RedisError

from config import settings

logger = logging.getLogger(__name__)

# Pool global lazy — se inicializa en `_get_client` la primera vez.
# NO instanciamos al import porque eso rompe tests que monkeypatchean.
_client: Redis | None = None


def _get_client() -> Redis:
    """Devuelve el cliente Redis global, creandolo en el primer llamado.

    `from_url` con asyncio retorna un cliente con pool interno (default
    `max_connections=2**31` — efectivamente sin tope). No lo limitamos
    aca porque Fase 1 tiene un solo worker; en Fase 2 con Celery vamos
    a tunear esto en base a profiling real.
    """
    global _client
    if _client is None:
        _client = redis_async.from_url(
            settings.redis_url,
            decode_responses=False,
        )
    return _client


async def ping(timeout_s: float = 1.0) -> bool:
    """Verifica conectividad con Redis dentro del timeout dado.

    Args:
        timeout_s: tope total para que Redis responda PONG. Default 1s
            porque este metodo lo llama el endpoint /health, que se invoca
            cada N segundos desde un load balancer y NO puede bloquear.

    Returns:
        True si Redis respondio PONG dentro del timeout. False en cualquier
        otro caso (timeout, red caida, auth incorrecta, server abajo).

    NO levanta nunca — el endpoint /health depende de eso.
    """
    try:
        client = _get_client()
        return await asyncio.wait_for(client.ping(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("redis ping timeout after %.1fs", timeout_s)
        return False
    except RedisError as exc:
        logger.warning("redis ping failed: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001 — defensivo, el caller no debe romper
        logger.warning("redis ping unexpected error: %s", exc)
        return False


async def close() -> None:
    """Cierra el cliente global. Pensado para shutdown del app o teardown de tests.

    Idempotente — llamarlo dos veces no rompe.
    """
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None


# ---------------------------------------------------------------------------
# B1: Capa 1 — hash lookup y almacenamiento
# ---------------------------------------------------------------------------

_HASH_PREFIX = "comp:hash:"
_HASH_TTL_DAYS = 7


async def check_hash(sha256: str) -> _uuid.UUID | None:
    """Comprueba si un hash SHA-256 existe en la cache Redis.

    Retorna el UUID del comprobante si se encontro, None si no existe o
    ante cualquier error de Redis. Nunca levanta.

    Patron: Capa 1 miss → pipeline continua hacia Capa 2 (DB).

    Args:
        sha256: Hex SHA-256 del documento (64 chars).

    Returns:
        UUID del comprobante existente, o None en miss/error.
    """
    try:
        client = _get_client()
        value = await client.get(f"{_HASH_PREFIX}{sha256}")
        if value is None:
            return None
        # Redis almacena con decode_responses=False → bytes o str
        decoded = value.decode() if isinstance(value, bytes) else value
        return _uuid.UUID(decoded)
    except Exception:  # noqa: BLE001 — defensivo, nunca interrumpir pipeline
        return None


async def set_hash(
    sha256: str, comp_id: _uuid.UUID, ttl_days: int = _HASH_TTL_DAYS
) -> None:
    """Almacena un mapeo SHA-256 → UUID en Redis con TTL.

    Fire-and-forget: nunca levanta. Fallos de Redis son silenciados.
    El TTL por defecto es 7 dias (604800 segundos).

    Args:
        sha256: Hex SHA-256 del documento.
        comp_id: UUID del comprobante recien insertado.
        ttl_days: Tiempo de vida en dias. Default 7.
    """
    try:
        client = _get_client()
        await client.set(
            f"{_HASH_PREFIX}{sha256}",
            str(comp_id),
            ex=ttl_days * 86400,
        )
    except Exception:  # noqa: BLE001 — fire-and-forget
        pass

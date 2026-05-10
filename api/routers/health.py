"""Endpoint /health — chequeo consolidado de las 3 dependencias criticas.

Fase 1 (task 1.7.2): el endpoint chequea llama-server, postgres y redis
EN PARALELO con `asyncio.gather` y devuelve siempre 200 con un
`HealthResponse`. El HTTP indica "la API responde"; los flags `ok` por
servicio indican que dependencia esta degradada.

Por que paralelo: si los 3 chequeos fueran secuenciales con 1s de timeout
cada uno, el peor caso es ~3s. En paralelo es max(individuales). Esto
importa porque /health lo invoca un load balancer cada N segundos y un
endpoint lento bloquea recursos.

Por que 200 incluso con todos los flags en False: el codigo HTTP indica
disponibilidad de la API, no salud del sistema. Si devolvieramos 503
ante "redis caido", un load balancer agresivo nos sacaria de rotacion
aun cuando el flow principal (sin cache) seguiria funcionando. Esa
politica de "tolerancia a degradacion" la decide el cliente, no nosotros.
La unica razon para devolver !=200 seria que la API no pueda armar el
response (caso patologico — el framework lo maneja con 5xx automatico).
"""

from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_session
from schemas.health import HealthResponse, ServiceCheck
from services import cache_service

router = APIRouter(tags=["health"])

# Timeout por chequeo individual. Mantener bajo: el endpoint corre en el
# hot-path de healthchecks de load balancer. Si una dependencia tarda mas
# que esto preferimos reportar `ok=False` y dejar que el cliente decida.
_CHECK_TIMEOUT_S = 1.0


def _ms(t0: float) -> str:
    """Formatea elapsed desde t0 (perf_counter) como 'XXms' para `detail`."""
    return f"{(time.perf_counter() - t0) * 1000:.0f}ms"


async def _check_llama() -> ServiceCheck:
    """GET /health a llama-server con timeout corto.

    Usa un httpx.AsyncClient efimero porque el endpoint health es de baja
    frecuencia y no justifica un pool global. Si en Fase 5 vemos contention
    movemos esto a un cliente compartido.
    """
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=settings.llama_server_url,
            timeout=_CHECK_TIMEOUT_S,
        ) as client:
            response = await client.get("/health")
        if response.status_code == 200:
            return ServiceCheck(ok=True, detail=_ms(t0))
        return ServiceCheck(
            ok=False,
            detail=f"http {response.status_code} ({_ms(t0)})",
        )
    except httpx.TimeoutException:
        return ServiceCheck(ok=False, detail=f"timeout >{_CHECK_TIMEOUT_S}s")
    except httpx.RequestError as exc:
        return ServiceCheck(ok=False, detail=f"network error: {exc}")
    except Exception as exc:  # noqa: BLE001 — el endpoint no debe romper
        return ServiceCheck(ok=False, detail=f"unexpected: {exc}")


async def _check_db(session: AsyncSession) -> ServiceCheck:
    """SELECT 1 en la sesion async. Mide latencia para `detail`."""
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(
            session.execute(text("SELECT 1")),
            timeout=_CHECK_TIMEOUT_S,
        )
        return ServiceCheck(ok=True, detail=_ms(t0))
    except asyncio.TimeoutError:
        return ServiceCheck(ok=False, detail=f"timeout >{_CHECK_TIMEOUT_S}s")
    except Exception as exc:  # noqa: BLE001 — el endpoint no debe romper
        return ServiceCheck(ok=False, detail=f"db error: {exc}")


async def _check_redis() -> ServiceCheck:
    """Delega en cache_service.ping (que ya es safe — nunca levanta)."""
    t0 = time.perf_counter()
    ok = await cache_service.ping(timeout_s=_CHECK_TIMEOUT_S)
    detail = _ms(t0) if ok else f"ping failed (>{_CHECK_TIMEOUT_S}s o error)"
    return ServiceCheck(ok=ok, detail=detail)


@router.get("/health", response_model=HealthResponse)
async def health(
    session: AsyncSession = Depends(get_session),
) -> HealthResponse:
    """Health check consolidado: llama-server, postgres y redis en paralelo.

    Siempre 200. Los flags `ok` por servicio indican que dependencia esta
    degradada. Ver docstring del modulo para la justificacion.
    """
    llama_check, db_check, redis_check = await asyncio.gather(
        _check_llama(),
        _check_db(session),
        _check_redis(),
        return_exceptions=False,
    )
    return HealthResponse(
        llama=llama_check,
        db=db_check,
        redis=redis_check,
    )

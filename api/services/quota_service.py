"""Servicio de verificacion de cuota mensual (R-74).

Unico punto donde se lee PLAN_LIMITS y se cuenta el uso mensual de uploads.
Si la cuota fue superada, levanta HTTP 429 con detalle estructurado.

Decisiones:
- Sin estado (stateless function) — facil de mockear en tests.
- La consulta usa fecha_registro >= inicio_del_mes (UTC) para consistencia.
- reset_date es siempre el primer dia del mes siguiente (ISO 8601).
- No incrementa contador — solo lee; el INSERT de Comprobante es el contador.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import PLAN_LIMITS
from models.comprobante import Comprobante
from models.usuario import Usuario


async def check_quota(usuario: Usuario, session: AsyncSession) -> None:
    """Verifica que el usuario no haya superado su cuota mensual.

    Args:
        usuario: Usuario ORM con campos .plan y .sin_cuota.
        session: AsyncSession para consultar comprobantes del mes.

    Returns:
        None si el usuario puede subir (cuota disponible o exento).

    Raises:
        HTTPException(429): Si el usuario supero su limite mensual.
            detail = {used, limit, plan, reset_date}
    """
    # Fast-path 1: usuario exento de cuota (e.g., system@smartvoucher.local)
    if usuario.sin_cuota:
        return None

    limit = PLAN_LIMITS.get(usuario.plan, 0)

    # Fast-path 2: plan ilimitado (enterprise)
    if limit == -1:
        return None

    # Calcular inicio del mes actual en UTC
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Contar uploads del usuario en el mes actual
    stmt = select(func.count()).where(
        Comprobante.id_usuario == usuario.id_usuario,
        Comprobante.fecha_registro >= month_start,
    )
    result = await session.execute(stmt)
    used = result.scalar()

    if used >= limit:
        # Calcular primer dia del mes siguiente (reset_date)
        if now.month == 12:
            reset_date = date(now.year + 1, 1, 1).isoformat()
        else:
            reset_date = date(now.year, now.month + 1, 1).isoformat()

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "used": used,
                "limit": limit,
                "plan": usuario.plan,
                "reset_date": reset_date,
            },
        )

    return None


async def get_quota_usage(usuario: Usuario, session: AsyncSession) -> dict:
    """Devuelve el uso de cuota del mes actual sin lanzar excepcion.

    Usado por GET /web/auth/quota para que el frontend muestre
    el medidor de uso sin necesitar que falle un upload primero.

    Returns:
        dict con keys: used, limit, plan, reset_date, unlimited (bool)
    """
    if usuario.sin_cuota:
        return {
            "used": 0,
            "limit": -1,
            "plan": usuario.plan,
            "reset_date": None,
            "unlimited": True,
        }

    limit = PLAN_LIMITS.get(usuario.plan, 0)

    if limit == -1:
        return {
            "used": 0,
            "limit": -1,
            "plan": usuario.plan,
            "reset_date": None,
            "unlimited": True,
        }

    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    stmt = select(func.count()).where(
        Comprobante.id_usuario == usuario.id_usuario,
        Comprobante.fecha_registro >= month_start,
    )
    result = await session.execute(stmt)
    used = result.scalar()

    if now.month == 12:
        reset_date = date(now.year + 1, 1, 1).isoformat()
    else:
        reset_date = date(now.year, now.month + 1, 1).isoformat()

    return {
        "used": used,
        "limit": limit,
        "plan": usuario.plan,
        "reset_date": reset_date,
        "unlimited": False,
    }

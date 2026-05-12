"""Web stats router — GET /web/stats/

Returns org-scoped month-to-date KPI aggregates for the dashboard (R-37).
Protected by require_jwt. All queries are scoped to usuario.id_organizacion.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from dependencies.auth_jwt import require_jwt
from models.comprobante import Comprobante
from models.usuario import Usuario
from schemas.web import StatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web/stats", tags=["web-stats"])


@router.get(
    "/",
    response_model=StatsResponse,
    summary="Org-scoped month-to-date KPI stats",
    dependencies=[Depends(require_jwt)],
)
async def get_stats(
    usuario: Usuario = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> StatsResponse:
    """Return month-to-date KPI aggregates scoped to the authenticated user's org.

    Scenarios covered: S-23, S-24, S-26.

    - total_mes: total comprobantes submitted this calendar month for the org.
    - duplicados_mes: count where estado_actual = 'duplicado'.
    - tasa_error: duplicados_mes / total_mes * 100 (0.0 when total == 0).
    """
    today = date.today()
    month_start = today.replace(day=1)

    try:
        # Build a sub-query joining comprobantes → usuarios to scope by org.
        stmt_total = (
            select(func.count(Comprobante.id_comprobante))
            .join(Usuario, Comprobante.id_usuario == Usuario.id_usuario)
            .where(
                Usuario.id_organizacion == usuario.id_organizacion,
                Comprobante.fecha_registro >= month_start,
                Comprobante.deleted_at.is_(None),
            )
        )

        stmt_duplicados = (
            select(func.count(Comprobante.id_comprobante))
            .join(Usuario, Comprobante.id_usuario == Usuario.id_usuario)
            .where(
                Usuario.id_organizacion == usuario.id_organizacion,
                Comprobante.fecha_registro >= month_start,
                Comprobante.estado_actual == "duplicado",
                Comprobante.deleted_at.is_(None),
            )
        )

        total_result = await db.execute(stmt_total)
        dup_result = await db.execute(stmt_duplicados)

        total_mes: int = total_result.scalar_one() or 0
        duplicados_mes: int = dup_result.scalar_one() or 0
        tasa_error = (duplicados_mes / total_mes * 100) if total_mes > 0 else 0.0

    except Exception as exc:
        # S-26: graceful 500 — log internally, return structured error.
        logger.exception("Stats query failed for org %s: %s", usuario.id_organizacion, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving stats",
        ) from exc

    return StatsResponse(
        total_mes=total_mes,
        duplicados_mes=duplicados_mes,
        tasa_error=round(tasa_error, 2),
    )

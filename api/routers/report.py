"""GET /report — aggregate counts of comprobantes by estado.

Returns:
  - total_comprobantes: count of all non-deleted comprobantes for SYSTEM_USER_ID
  - por_estado: list of {estado, total} pairs
  - promedio_score_similitud: avg of non-null scores in validaciones (or None)

Note Fase 4: Replace SYSTEM_USER_ID filter with JWT org/user scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.comprobante import Comprobante
from models.seed import SYSTEM_USER_ID
from models.validacion import Validacion
from schemas.report import EstadoCount, ReportResponse

router = APIRouter(prefix="/report", tags=["report"])


@router.get("", response_model=ReportResponse)
async def get_report(session: AsyncSession = Depends(get_session)) -> ReportResponse:
    """Return aggregate counts of comprobantes by estado.

    Scope: comprobantes for SYSTEM_USER_ID (Fase 4: replace with JWT org).
    Excludes soft-deleted comprobantes.
    """
    # Count per estado
    rows = await session.execute(
        select(Comprobante.estado_actual, func.count().label("total"))
        .where(
            Comprobante.id_usuario == SYSTEM_USER_ID,
            Comprobante.deleted_at.is_(None),
        )
        .group_by(Comprobante.estado_actual)
        .order_by(Comprobante.estado_actual)
    )
    counts = [EstadoCount(estado=r.estado_actual, total=r.total) for r in rows]
    total = sum(c.total for c in counts)

    # Avg score from validaciones (for comprobantes owned by SYSTEM_USER_ID)
    score_row = await session.execute(
        select(func.avg(Validacion.score_similitud))
        .join(Comprobante, Validacion.id_comprobante == Comprobante.id_comprobante)
        .where(
            Comprobante.id_usuario == SYSTEM_USER_ID,
            Validacion.score_similitud.is_not(None),
        )
    )
    avg_score = score_row.scalar_one_or_none()

    return ReportResponse(
        total_comprobantes=total,
        por_estado=counts,
        promedio_score_similitud=float(avg_score) if avg_score is not None else None,
    )

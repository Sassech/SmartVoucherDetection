"""Web comprobantes router.

Endpoints:
  GET  /web/comprobantes/          — paginated list, org-scoped, filterable (R-39)
  GET  /web/comprobantes/{id}      — full detail, org check, 403 on foreign org (R-42, R-46)
  POST /web/comprobantes/{id}/decision — apply aceptar/rechazar, org check (R-44)

All endpoints are protected by require_jwt. Comprobantes from other orgs → 403.
"""

from __future__ import annotations

import uuid
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from dependencies.auth_jwt import require_jwt
from models.comprobante import Comprobante
from models.usuario import Usuario
from models.validacion import Validacion
from schemas.web import (
    DecisionRequest,
    DecisionResponse,
    WebComprobanteDetail,
    WebComprobanteResponse,
    WebListResponse,
)
from services.state_machine import InvalidTransitionError, apply_transition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web/comprobantes", tags=["web-comprobantes"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCION_TO_STATE: dict[str, str] = {
    "aceptar": "valido",
    "rechazar": "duplicado",
}


async def _get_comprobante_for_org(
    id_comprobante: uuid.UUID,
    usuario: Usuario,
    db: AsyncSession,
) -> Comprobante:
    """Fetch a Comprobante and verify it belongs to the authenticated user's org.

    Raises 404 if not found, 403 if foreign org.
    """
    stmt = (
        select(Comprobante)
        .where(
            Comprobante.id_comprobante == id_comprobante,
            Comprobante.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    comprobante = result.scalar_one_or_none()

    if comprobante is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comprobante not found")

    # Verify org ownership — must join through usuario FK (S-40, S-38).
    owner_stmt = select(Usuario.id_organizacion).where(
        Usuario.id_usuario == comprobante.id_usuario,
        Usuario.deleted_at.is_(None),
    )
    owner_result = await db.execute(owner_stmt)
    owner_org = owner_result.scalar_one_or_none()

    if owner_org != usuario.id_organizacion:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return comprobante


# ---------------------------------------------------------------------------
# GET /web/comprobantes/
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=WebListResponse,
    summary="Paginated comprobantes list (org-scoped)",
    dependencies=[Depends(require_jwt)],
)
async def list_comprobantes(
    usuario: Usuario = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> WebListResponse:
    """Return paginated, org-scoped comprobantes with optional filters.

    Scenarios: S-27, S-28, S-29, S-30, S-32.
    """
    # Base filter: org-scoped via join on usuario.id_organizacion.
    base_where = [
        Usuario.id_organizacion == usuario.id_organizacion,
        Comprobante.deleted_at.is_(None),
    ]
    if status_filter is not None:
        base_where.append(Comprobante.estado_actual == status_filter)
    if date_from is not None:
        base_where.append(Comprobante.fecha_deposito >= date_from)
    if date_to is not None:
        base_where.append(Comprobante.fecha_deposito <= date_to)

    # Count total for pagination metadata.
    count_stmt = (
        select(func.count(Comprobante.id_comprobante))
        .join(Usuario, Comprobante.id_usuario == Usuario.id_usuario)
        .where(*base_where)
    )
    count_result = await db.execute(count_stmt)
    total: int = count_result.scalar_one() or 0

    # Paginated rows.
    offset = (page - 1) * page_size
    rows_stmt = (
        select(Comprobante)
        .join(Usuario, Comprobante.id_usuario == Usuario.id_usuario)
        .where(*base_where)
        .order_by(Comprobante.fecha_registro.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows_result = await db.execute(rows_stmt)
    rows = rows_result.scalars().all()

    items = [WebComprobanteResponse.model_validate(row) for row in rows]

    return WebListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# GET /web/comprobantes/{id}
# ---------------------------------------------------------------------------

@router.get(
    "/{id_comprobante}",
    response_model=WebComprobanteDetail,
    summary="Comprobante detail (org-scoped)",
    dependencies=[Depends(require_jwt)],
)
async def get_comprobante(
    id_comprobante: uuid.UUID,
    usuario: Usuario = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> WebComprobanteDetail:
    """Return full comprobante record. 403 if foreign org (S-39, S-40)."""
    comprobante = await _get_comprobante_for_org(id_comprobante, usuario, db)
    return WebComprobanteDetail.model_validate(comprobante)


# ---------------------------------------------------------------------------
# POST /web/comprobantes/{id}/decision
# ---------------------------------------------------------------------------

@router.post(
    "/{id_comprobante}/decision",
    response_model=DecisionResponse,
    summary="Apply aceptar/rechazar decision (org-scoped)",
    dependencies=[Depends(require_jwt)],
)
async def apply_decision(
    id_comprobante: uuid.UUID,
    body: DecisionRequest,
    usuario: Usuario = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> DecisionResponse:
    """Apply a manual decision to a comprobante.

    - Verifies org ownership → 403 on foreign org (S-38).
    - Calls apply_transition() to validate state machine.
    - Creates a Validacion(metodo_deteccion="manual") record.
    - Returns updated estado_actual.

    Scenarios: S-38 (forbidden), R-44.
    """
    comprobante = await _get_comprobante_for_org(id_comprobante, usuario, db)

    target_state = _ACCION_TO_STATE[body.accion]

    try:
        apply_transition(comprobante, target_state)
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    # Record the manual validation event.
    validacion = Validacion(
        id_comprobante=comprobante.id_comprobante,
        id_usuario=usuario.id_usuario,
        clasificacion="valido" if body.accion == "aceptar" else "duplicado",
        metodo_deteccion="manual",
    )
    db.add(validacion)
    await db.flush()
    await db.refresh(comprobante)

    return DecisionResponse(
        id_comprobante=comprobante.id_comprobante,
        estado_actual=comprobante.estado_actual,
        mensaje=f"Comprobante marcado como {target_state}",
    )

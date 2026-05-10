"""CU-02: Manual validation — move a comprobante from en_revision to valido or duplicado.

POST /validate/{id}?clasificacion=valido|duplicado

Rules:
- Comprobante must exist and not be soft-deleted.
- Comprobante must be in 'en_revision' state.
- clasificacion must be "valido" or "duplicado".
- Creates a Validacion record with metodo_deteccion="manual".
- Returns the updated ComprobanteResponse (200).

Note Fase 4: Replace SYSTEM_USER_ID with the authenticated user from JWT.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from dependencies.auth_api_key import require_api_key
from models.comprobante import Comprobante
from models.usuario import Usuario
from models.validacion import Validacion
from schemas.comprobante import ComprobanteResponse
from services.state_machine import InvalidTransitionError, apply_transition

router = APIRouter(prefix="/validate", tags=["validation"])


@router.post(
    "/{comprobante_id}",
    response_model=ComprobanteResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_comprobante(
    comprobante_id: uuid.UUID,
    clasificacion: str,  # Query param: "valido" or "duplicado"
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(require_api_key),
) -> ComprobanteResponse:
    """Manually validate a comprobante that is in 'en_revision' state.

    Query params:
        clasificacion: "valido" or "duplicado"

    Raises:
        422: If clasificacion is not "valido" or "duplicado".
        404: If comprobante is not found or soft-deleted.
        409: If comprobante is not in 'en_revision' state.
    """
    if clasificacion not in ("valido", "duplicado"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="clasificacion must be 'valido' or 'duplicado'",
        )

    result = await session.execute(
        select(Comprobante).where(
            Comprobante.id_comprobante == comprobante_id,
            Comprobante.deleted_at.is_(None),
        )
    )
    comp = result.scalar_one_or_none()
    if comp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comprobante not found",
        )

    try:
        apply_transition(comp, clasificacion)
    except InvalidTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot transition from '{e.from_state}' to '{e.to_state}'. "
                "Comprobante must be in 'en_revision'."
            ),
        )

    val = Validacion(
        id_comprobante=comp.id_comprobante,
        id_usuario=usuario.id_usuario,
        clasificacion=clasificacion,
        metodo_deteccion="manual",
    )
    session.add(val)
    await session.commit()
    await session.refresh(comp)

    return ComprobanteResponse.from_orm_model(comp)

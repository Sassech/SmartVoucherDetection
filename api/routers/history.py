"""Endpoint GET /history — listado paginado de comprobantes (task 1.7.3).

Filtros opcionales:
- `fecha_desde`, `fecha_hasta` → sobre `fecha_deposito` (lo que el comprobante
  DICE, no cuando se subio). Es lo que el contador busca: "depositos de marzo".
- `banco` → match exacto contra el banco normalizado (BBVA, Citibanamex, ...).
  Asumimos que el frontend envia el valor canonico del catalogo.
- `estado` → match exacto contra `ESTADOS_VALIDOS`. Validado en el query param.

Paginacion offset+limit (decision tomada en sesion 2026-05-09):
- `limit`: default 20, max 100. Cualquier intento >100 → 422.
- `offset`: default 0, sin tope (el cliente puede paginar tan profundo como
  quiera; en Fase 5 si vemos performance issue se acota).
- `total` lo devolvemos en el response para que el frontend pinte
  "Pagina 3 de 47" sin un segundo request.

Multi-tenant: hardcodeado a `SYSTEM_USER_ID` igual que /upload-slip. Cuando
llegue auth en Fase 4, se reemplaza por el `request.user.id_usuario` del JWT
SIN cambiar el contrato HTTP.

Soft delete: filtramos `deleted_at IS NULL` siempre. Los comprobantes
soft-deleted son visibles solo via endpoint de auditoria (Fase 4+).

Orden: `fecha_registro DESC` — los mas recientes primero. Es lo que un
operador espera al abrir el historial.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from dependencies.auth_api_key import require_api_key
from models.comprobante import ESTADOS_VALIDOS, Comprobante
from models.usuario import Usuario
from schemas.comprobante import ComprobanteListResponse, ComprobanteResponse

router = APIRouter(tags=["history"])

# Tope superior de `limit`. Hardcodeado; si en Fase 4 algun plan empresarial
# necesita exportar mas, sumamos endpoint /export con streaming.
_MAX_LIMIT = 100


@router.get("/history", response_model=ComprobanteListResponse)
async def history(
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(require_api_key),
    limit: int = Query(
        20,
        ge=1,
        le=_MAX_LIMIT,
        description="Cantidad maxima de items por pagina (1-100).",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Cantidad de items a saltear (paginacion).",
    ),
    fecha_desde: date | None = Query(
        None,
        description="Filtra comprobantes con fecha_deposito >= este valor (ISO 8601).",
    ),
    fecha_hasta: date | None = Query(
        None,
        description="Filtra comprobantes con fecha_deposito <= este valor (ISO 8601).",
    ),
    banco: str | None = Query(
        None,
        max_length=50,
        description="Match exacto contra banco normalizado (e.g. 'BBVA', 'OTRO').",
    ),
    estado: str | None = Query(
        None,
        description=f"Estado actual. Validos: {ESTADOS_VALIDOS}",
    ),
) -> ComprobanteListResponse:
    """Devuelve una pagina de comprobantes del usuario actual con filtros opcionales."""

    # Validacion cruzada que `Query()` no puede expresar.
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="fecha_desde no puede ser mayor que fecha_hasta",
        )
    if estado is not None and estado not in ESTADOS_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"estado invalido: {estado!r}. Validos: {ESTADOS_VALIDOS}",
        )

    # Construimos la WHERE base UNA sola vez y la reusamos para count y para
    # el SELECT paginado. Asi nos garantizamos que `total` y `items` estan
    # alineados con los mismos predicados.
    base_filters = [
        Comprobante.id_usuario == usuario.id_usuario,
        Comprobante.deleted_at.is_(None),  # soft delete
    ]
    if fecha_desde is not None:
        base_filters.append(Comprobante.fecha_deposito >= fecha_desde)
    if fecha_hasta is not None:
        base_filters.append(Comprobante.fecha_deposito <= fecha_hasta)
    if banco is not None:
        base_filters.append(Comprobante.banco == banco)
    if estado is not None:
        base_filters.append(Comprobante.estado_actual == estado)

    # COUNT para `total`. Usamos `func.count()` con expresion dummy (no
    # `count(*)` porque SQLAlchemy lo traduce raro) — el optimizer de
    # Postgres lo resuelve igual de eficiente con los indices existentes.
    count_stmt = select(func.count()).select_from(Comprobante).where(*base_filters)
    total = (await session.execute(count_stmt)).scalar_one()

    # Si el offset cae fuera del total, devolvemos lista vacia (NO 404). Es
    # lo que un cliente paginando esperaria — un 404 confunde con "el recurso
    # no existe".
    items_orm = []
    if offset < total:
        # Tiebreaker `id_comprobante DESC`: si varios comprobantes caen en el
        # mismo `func.now()` (insert masivo en el mismo tick), el UUID v7 es
        # ordenable por tiempo y rompe el empate de forma estable. Sin esto
        # la paginacion podria duplicar/saltearse filas entre paginas.
        items_stmt = (
            select(Comprobante)
            .where(*base_filters)
            .order_by(
                Comprobante.fecha_registro.desc(),
                Comprobante.id_comprobante.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        items_orm = (await session.execute(items_stmt)).scalars().all()

    return ComprobanteListResponse(
        items=[ComprobanteResponse.from_orm_model(c) for c in items_orm],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items_orm) < total,
    )


@router.get("/comprobante/{id_comprobante}", response_model=ComprobanteResponse)
async def get_comprobante(
    id_comprobante: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _usuario: Usuario = Depends(require_api_key),
) -> ComprobanteResponse:
    """Devuelve un comprobante por su UUID.

    Usado principalmente por el plugin WordPress para enriquecer la fila de
    un duplicado con los datos del comprobante original (monto, banco, fecha,
    referencia) sin hacer un scan completo de /history.

    Returns 404 si el id no existe o fue soft-deleted.
    """
    stmt = select(Comprobante).where(
        Comprobante.id_comprobante == id_comprobante,
        Comprobante.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    comprobante = result.scalar_one_or_none()

    if comprobante is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comprobante {id_comprobante} not found.",
        )

    return ComprobanteResponse.from_orm_model(comprobante)

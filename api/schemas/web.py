"""Schemas for web routes (web_comprobantes, web_stats).

These Pydantic models are used exclusively by the /web/ endpoints
protected by require_jwt. They are separate from the plugin-facing
schemas in comprobante.py and validacion.py.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class WebComprobanteResponse(BaseModel):
    """Summary row used in the paginated list endpoint."""

    id_comprobante: uuid.UUID
    imagen_path: str
    referencia: str | None
    monto: Decimal | None
    fecha_deposito: date | None
    banco: str | None
    estado_actual: str
    fecha_registro: datetime

    model_config = {"from_attributes": True}


class WebComprobanteDetail(WebComprobanteResponse):
    """Full record used in the detail endpoint (R-42, R-46)."""

    texto_extraido: str | None
    numero_operacion: str | None


class WebListResponse(BaseModel):
    """Generic paginated list wrapper (R-39)."""

    items: list[WebComprobanteResponse]
    total: int
    page: int
    page_size: int

    @computed_field  # type: ignore[misc]
    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


class DecisionRequest(BaseModel):
    """Payload for POST /web/comprobantes/{id}/decision (R-44)."""

    accion: Literal["aceptar", "rechazar"]
    motivo: str | None = Field(default=None, max_length=500)


class DecisionResponse(BaseModel):
    """Confirmation returned after applying a decision."""

    id_comprobante: uuid.UUID
    estado_actual: str
    mensaje: str


class StatsResponse(BaseModel):
    """Org-scoped month-to-date KPI stats (R-37)."""

    total_mes: int
    duplicados_mes: int
    tasa_error: float = Field(
        description="Percentage of duplicados over total (0.0 if total == 0)"
    )

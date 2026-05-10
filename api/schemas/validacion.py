"""Schemas Pydantic v2 para Validacion (CU-02 y auditoria).

`ValidacionResponse`: DTO de salida para registros de validacion.
  - `from_attributes=True` permite construir desde el ORM.
  - `id_comprobante_original` es nullable (Capa 2/3 lo setea; manual no siempre).
  - `score_similitud` es nullable (hash_exacto y campos_exactos no tienen score).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ValidacionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id_validacion: uuid.UUID
    id_comprobante: uuid.UUID
    id_comprobante_original: uuid.UUID | None
    clasificacion: str
    metodo_deteccion: str
    score_similitud: float | None
    fecha_validacion: datetime

"""Schemas Pydantic v2 para el endpoint GET /report.

`EstadoCount`: par (estado, total) del COUNT(*) GROUP BY estado_actual.
`ReportResponse`: respuesta completa del reporte agregado.

`promedio_score_similitud`:
  - Promedio de `score_similitud` de todas las validaciones no-NULL
    correspondientes a comprobantes del sistema.
  - None cuando no hay validaciones con score (p.ej. solo hash_exacto).

Nota Fase 4: cuando haya multi-tenancy real, estos campos se escopen
por `id_usuario` / `id_organizacion` del JWT. Por ahora, global.
"""

from __future__ import annotations

from pydantic import BaseModel


class EstadoCount(BaseModel):
    estado: str
    total: int


class ReportResponse(BaseModel):
    total_comprobantes: int
    por_estado: list[EstadoCount]
    promedio_score_similitud: float | None  # avg de score_similitud no-null

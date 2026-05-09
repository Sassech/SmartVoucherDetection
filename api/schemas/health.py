"""Schema del endpoint `/health` (1.7.2).

Modelo simple por dependencia con dos campos: `ok` (bool) y `detail` (str
opcional con info de la falla — ms de latencia, codigo de error, etc).
Esto permite que el cliente no tenga que parsear strings tipo "OK"/"FAIL"
y que el dashboard renderice un semaforo por servicio sin mas logica.

Disenio explicito: el `HealthResponse` NO tiene un boolean global agregado.
El cliente decide si "todos OK" significa salud total o si tolera un Redis
caido (ej. en Fase 1 sin cache podria seguir funcionando degradado).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ServiceCheck(BaseModel):
    """Estado de un servicio externo individual."""

    model_config = ConfigDict(frozen=True)

    ok: bool = Field(description="True si el servicio respondio dentro del timeout.")
    detail: str | None = Field(
        default=None,
        description=(
            "Info adicional: latencia (e.g. '12ms'), version, o mensaje de error. "
            "Pensado para humanos en logs/dashboard, no para parsing."
        ),
    )


class HealthResponse(BaseModel):
    """Estado consolidado de las 3 dependencias criticas de Fase 1.

    El endpoint debe responder 200 incluso si algun `ok=False`: el codigo
    HTTP indica que la API responde, los flags indican que dependencia esta
    degradada. Si la API no puede armar el response → 503 (manejado fuera
    del schema).
    """

    model_config = ConfigDict(frozen=True)

    llama: ServiceCheck = Field(
        description="llama-server (GLM-OCR) — chequeado via GET /health."
    )
    db: ServiceCheck = Field(
        description="PostgreSQL — chequeado via SELECT 1 async."
    )
    redis: ServiceCheck = Field(
        description="Redis — chequeado via PING."
    )

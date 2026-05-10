"""Schemas Pydantic v2 del recurso Comprobante.

Tres DTOs con responsabilidades separadas (no reusar uno solo):

- `CamposExtraidos`: payload normalizado post-parser_service. Es lo que el
  endpoint de upload devuelve al cliente y lo que se persiste en columnas
  del modelo `Comprobante`. Los crudos del OCR (str/number/None) NO viven
  aca — esos son un dict suelto en `ocr_service.extract_fields`.

- `ComprobanteCreate`: DTO interno (capa servicio → repo). Junta los campos
  que el endpoint conoce ANTES de hacer `INSERT`: usuario, archivo,
  texto_extraido, hash y los `CamposExtraidos`. NO incluye `id_comprobante`
  ni `fecha_registro` (los pone la DB).

- `ComprobanteResponse`: DTO de salida hacia HTTP. Incluye id, timestamps y
  expone `campos_extraidos` como objeto anidado (mejor DX que aplanar 5
  columnas en el response). `from_attributes=True` permite construir desde
  el ORM via `ComprobanteResponse.from_orm_model(...)` (ver helper).

Decision Decimal vs float en monto:
Pydantic v2 acepta `Decimal` nativo y lo serializa a string en JSON
(`"123.45"`). Es lo correcto para dinero — mandar `123.45` como float
expone al cliente al mismo bug de precision binaria que evitamos en DB.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.comprobante import ESTADOS_VALIDOS


def _validate_estado(value: str) -> str:
    """Helper compartido entre Create y Response.

    Mantiene el contrato sincronizado con el CHECK de la DB sin importar
    en runtime el modulo del modelo (evita ciclos si algun dia el ORM
    importa schemas).
    """
    if value not in ESTADOS_VALIDOS:
        raise ValueError(
            f"estado_actual invalido: {value!r}. Validos: {ESTADOS_VALIDOS}"
        )
    return value


class CamposExtraidos(BaseModel):
    """Campos del comprobante despues de pasar por parser_service.

    Casi todos los campos son `Optional` porque el OCR puede no detectarlos
    y el parser devuelve `None` ante input invalido (D-10). El unico siempre
    presente es `banco`: `normalize_banco` cae a `"OTRO"` como fallback.
    """

    model_config = ConfigDict(frozen=True)

    monto: Decimal | None = Field(
        default=None,
        description="Monto en moneda local. Numeric(15,2) en DB.",
        max_digits=15,
        decimal_places=2,
        ge=0,
    )
    fecha: date | None = Field(
        default=None,
        description="Fecha del deposito (sin hora) parseada por dateutil.",
    )
    referencia: str | None = Field(
        default=None,
        max_length=100,
        description="Referencia bancaria normalizada (uppercase, sin espacios extra).",
    )
    numero_operacion: str | None = Field(
        default=None,
        max_length=100,
        description="Numero de operacion / folio interno del banco. Crudo del OCR.",
    )
    banco: str = Field(
        max_length=50,
        description=(
            "Banco normalizado contra catalogo (BBVA, Citibanamex, Banorte, HSBC, "
            "Santander, Hey Banco, Nu Bank, OTRO). Nunca null — fallback 'OTRO'."
        ),
    )


class ComprobanteCreate(BaseModel):
    """Input al repositorio para INSERT. Capa servicio → DB.

    No se expone a HTTP. El endpoint construye este DTO tras correr OCR +
    parser, y el repo lo traduce a un `Comprobante` ORM.
    """

    model_config = ConfigDict(frozen=True)

    id_usuario: uuid.UUID
    imagen_path: str = Field(
        max_length=500,
        description="Ruta donde se guardo el archivo original (filesystem o S3).",
    )
    texto_extraido: str | None = Field(
        default=None,
        description="Texto bruto que el LLM puso en `content` antes del JSON parse.",
    )
    hash_documento: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 hex (lowercase) sobre los bytes ORIGINALES del upload.",
    )
    campos: CamposExtraidos
    estado_actual: str = Field(
        default="recibido",
        description=(
            "Estado inicial. El endpoint sincrono de Fase 1 setea 'recibido' y "
            "el servicio puede pasar a 'valido'/'error' antes del commit."
        ),
    )

    @field_validator("estado_actual")
    @classmethod
    def _check_estado(cls, v: str) -> str:
        return _validate_estado(v)


class ComprobanteResponse(BaseModel):
    """DTO de salida HTTP. Construible desde un ORM con `from_orm_model`.

    `campos_extraidos` se anida como objeto en lugar de aplanar las 5
    columnas — mejor DX para clientes y evita ambiguedad si alguna vez
    agregamos campos no-OCR al modelo (ej. anti-fraude scoring).

    NOTA: `from_attributes=True` solo, NO basta para componer
    `campos_extraidos` desde columnas planas del ORM. Por eso el helper
    `from_orm_model` arma el sub-objeto a mano.
    """

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id_comprobante: uuid.UUID
    id_usuario: uuid.UUID
    estado_actual: str
    hash_documento: str
    imagen_path: str
    fecha_registro: datetime
    campos_extraidos: CamposExtraidos

    @field_validator("estado_actual")
    @classmethod
    def _check_estado(cls, v: str) -> str:
        return _validate_estado(v)

    @classmethod
    def from_orm_model(cls, comp) -> "ComprobanteResponse":
        """Construye el response desde un `Comprobante` ORM.

        El nombre de columna `fecha_deposito` se mapea a `fecha` en el
        schema (mas corto y coherente con el OCR/parser).
        """
        return cls(
            id_comprobante=comp.id_comprobante,
            id_usuario=comp.id_usuario,
            estado_actual=comp.estado_actual,
            hash_documento=comp.hash_documento,
            imagen_path=comp.imagen_path,
            fecha_registro=comp.fecha_registro,
            campos_extraidos=CamposExtraidos(
                monto=comp.monto,
                fecha=comp.fecha_deposito,
                referencia=comp.referencia,
                numero_operacion=comp.numero_operacion,
                banco=comp.banco or "OTRO",
            ),
        )


class ComprobanteListResponse(BaseModel):
    """Pagina de comprobantes con metadata (task 1.7.3 — GET /history).

    Estrategia offset/limit. `total` es el COUNT(*) de la query con filtros
    aplicados (sin paginar) — permite que el frontend muestre "Pagina 3 de
    47" sin un segundo round-trip. Es O(n) en Postgres pero con los indices
    de Fase 1 (id_usuario, fecha_deposito, estado_actual) y filtro por
    usuario, el dataset por tenant raramente pasa de unos miles de filas.
    Si en Fase 5 vemos lentitud, migramos a estimaciones via `pg_class`.
    """

    model_config = ConfigDict(frozen=True)

    items: list[ComprobanteResponse] = Field(
        description="Comprobantes de la pagina actual, ordenados por fecha_registro DESC.",
    )
    total: int = Field(
        ge=0,
        description="Total de filas que matchean los filtros (sin paginar).",
    )
    limit: int = Field(ge=1, le=100, description="Tope de items por pagina.")
    offset: int = Field(ge=0, description="Cantidad de items salteados.")
    has_more: bool = Field(
        description="True si hay mas paginas despues de esta (offset+limit < total).",
    )

"""Modelo Comprobante — entidad central del dominio.

Decisiones de tipos:
- `monto`: `Numeric(15, 2)` — NUNCA Float en dinero (errores de precision binaria).
- `fecha_deposito`: `Date` (sin hora, viene del comprobante).
- `hash_documento`: SHA-256 hex = 64 chars exactos. UNIQUE para Capa 1 de
  deteccion de duplicados (Fase 2.1).
- `texto_extraido`: `Text` (sin limite — depende del modelo OCR).
- `estado_actual`: maquina de estados del plan. CHECK fuerte en DB; la
  transicion logica vive en `services/state_machine.py` (Fase 2.6).

Indices Fase 1:
- `id_usuario` (FK)
- `hash_documento` UNIQUE (Capa 1)
- `fecha_deposito` btree (filtros de historial)
- `estado_actual` btree (filtros de dashboard)

Indice compuesto `(referencia, monto, fecha_deposito)` queda para 2.2.2 cuando
se implemente Capa 2.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from database import Base

from ._mixins import SoftDeleteMixin

# Estados de la maquina (referencia: cosas/diagrama_estados.svg + plan §1.4).
ESTADOS_VALIDOS = (
    "recibido",
    "procesando",
    "comparando",
    "en_revision",
    "valido",
    "duplicado",
    "error",
)


class Comprobante(Base, SoftDeleteMixin):
    __tablename__ = "comprobantes"

    id_comprobante: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )
    id_usuario: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    imagen_path: Mapped[str] = mapped_column(String(500), nullable=False)
    texto_extraido: Mapped[str | None] = mapped_column(Text, nullable=True)
    referencia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    monto: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    fecha_deposito: Mapped[date | None] = mapped_column(
        Date, nullable=True, index=True
    )
    numero_operacion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    banco: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hash_documento: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    estado_actual: Mapped[str] = mapped_column(
        String(20), nullable=False, default="recibido", index=True
    )
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        back_populates="comprobantes"
    )
    validaciones: Mapped[list["Validacion"]] = relationship(  # noqa: F821
        back_populates="comprobante",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list["LogProcesamiento"]] = relationship(  # noqa: F821
        back_populates="comprobante",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            f"estado_actual IN {ESTADOS_VALIDOS!r}",
            name="ck_comprobantes_estado_actual",
        ),
        CheckConstraint(
            "monto IS NULL OR monto >= 0",
            name="ck_comprobantes_monto_no_negativo",
        ),
    )

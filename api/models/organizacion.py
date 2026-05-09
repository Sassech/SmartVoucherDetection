"""Modelo Organizacion — base multi-tenant (Fase 4 lo activa).

En Fase 1 cada despliegue tiene 1 sola organizacion (la del cliente).
La columna `id_organizacion` se propaga a Usuario/Comprobante via FK desde ya
para no tener que migrar datos cuando llegue Fase 4.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from database import Base

from ._mixins import SoftDeleteMixin

# Catalogo de planes (Fase 4 lo formaliza con Stripe). Por ahora sirve como
# guard rail: cualquier insert con valor distinto falla en DB.
PLANES_VALIDOS = ("basico", "profesional", "empresarial")


class Organizacion(Base, SoftDeleteMixin):
    __tablename__ = "organizaciones"

    id_organizacion: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    plan_suscripcion: Mapped[str] = mapped_column(
        String(50), nullable=False, default="basico"
    )
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones inversas
    usuarios: Mapped[list["Usuario"]] = relationship(  # noqa: F821
        back_populates="organizacion",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            f"plan_suscripcion IN {PLANES_VALIDOS!r}",
            name="ck_organizaciones_plan_suscripcion",
        ),
    )

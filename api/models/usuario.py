"""Modelo Usuario — pertenece a una Organizacion.

Decisiones:
- `contrasena_hash`: bcrypt hash (~60 chars, dejamos String(255) por las dudas).
- `token_api_hash`: bcrypt hash del API key personal (D-07). El plain solo se
  muestra al usuario UNA vez al generarlo. Nullable porque no todo usuario
  necesita API key (e.g., admin que solo entra por web).
- `rol`: CHECK constraint con valores fijos del plan (Fase 4).
- `correo`: UNIQUE global (no por organizacion) — invitaciones cross-org en Fase 4.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from database import Base

from ._mixins import SoftDeleteMixin

ROLES_VALIDOS = ("admin", "operador", "auditor")


class Usuario(Base, SoftDeleteMixin):
    __tablename__ = "usuarios"

    id_usuario: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )
    id_organizacion: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizaciones.id_organizacion", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str] = mapped_column(
        String(254), nullable=False, unique=True, index=True
    )
    contrasena_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="operador")
    token_api_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    organizacion: Mapped["Organizacion"] = relationship(  # noqa: F821
        back_populates="usuarios"
    )
    comprobantes: Mapped[list["Comprobante"]] = relationship(  # noqa: F821
        back_populates="usuario"
    )

    __table_args__ = (
        CheckConstraint(
            f"rol IN {ROLES_VALIDOS!r}",
            name="ck_usuarios_rol",
        ),
    )

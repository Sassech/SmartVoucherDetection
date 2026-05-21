"""ConfiguracionSistema — tabla clave/valor para configuracion del sistema.

Decisiones de diseno (D-16):
- PK natural VARCHAR(64) — las keys son identificadores semanticos legibles.
  No necesita UUID ni SoftDelete: los registros se crean en la migracion y
  se actualizan por admin; nunca se borran.
- `updated_at` con `server_default=func.now()` — poblado en INSERT por Postgres.
  `onupdate=func.now()` actualiza el valor en cada UPDATE via SQLAlchemy.
- NO SoftDeleteMixin: las entradas de configuracion son upsertables, no
  soft-deleteables.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ConfiguracionSistema(Base):
    """Tabla clave/valor para configuracion de la aplicacion."""

    __tablename__ = "configuracion_sistema"

    key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="Clave de configuracion (e.g. 'scoring.w_ref')",
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Valor de configuracion serializado como string",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Ultima actualizacion del registro",
    )

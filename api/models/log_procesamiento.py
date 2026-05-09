"""Modelo LogProcesamiento — auditoria tecnica de cada etapa del pipeline.

A diferencia del resto del modelo, NO tiene soft delete (D-06): los logs se
purgan por TTL/retencion, no se recuperan. Si bien `id_comprobante` cae en
CASCADE, esto es intencional — los logs huerfanos no aportan valor.

Niveles tipo syslog: INFO/WARN/ERROR. La etapa describe en que paso del
pipeline ocurrio (e.g., `ocr.request`, `parser.normalize`, `duplicate.layer1`).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from database import Base

NIVELES_VALIDOS = ("INFO", "WARN", "ERROR")


class LogProcesamiento(Base):
    __tablename__ = "log_procesamiento"

    id_log: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
    )
    id_comprobante: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comprobantes.id_comprobante", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_usuario: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="SET NULL"),
        nullable=True,
    )
    etapa: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    nivel: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    fecha_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    comprobante: Mapped["Comprobante"] = relationship(  # noqa: F821
        back_populates="logs"
    )

    __table_args__ = (
        CheckConstraint(
            f"nivel IN {NIVELES_VALIDOS!r}",
            name="ck_log_procesamiento_nivel",
        ),
    )

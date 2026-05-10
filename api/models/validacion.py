"""Modelo Validacion — historial de clasificaciones de un comprobante.

Cada vez que el sistema (o un humano via CU-02) clasifica un comprobante,
se inserta una fila acá. Permite trazar:
- por que se marco como duplicado (capa 1/2/3 + score)
- quien lo valido manualmente

`id_usuario` es nullable porque las detecciones automaticas no tienen autor.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from database import Base

from ._mixins import SoftDeleteMixin

# Coherente con plan §2.3.6.
CLASIFICACIONES_VALIDAS = ("valido", "sospechoso", "duplicado")

# Capas de deteccion del plan §2.1-2.3 + manual (CU-02).
METODOS_DETECCION_VALIDOS = (
    "hash_exacto",  # Capa 1 (Redis)
    "campos_exactos",  # Capa 2 (Postgres exact match)
    "scoring_ponderado",  # Capa 3 (Levenshtein + TF-IDF + numerico + temporal)
    "manual",  # CU-02 validacion humana
)


class Validacion(Base, SoftDeleteMixin):
    __tablename__ = "validaciones"

    id_validacion: Mapped[uuid.UUID] = mapped_column(
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
    id_comprobante_original: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("comprobantes.id_comprobante", ondelete="SET NULL"),
        nullable=True,
    )
    score_similitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    clasificacion: Mapped[str] = mapped_column(String(20), nullable=False)
    metodo_deteccion: Mapped[str] = mapped_column(String(30), nullable=False)
    fecha_validacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    # `foreign_keys` explicito porque hay dos FK a la misma tabla `comprobantes`
    # (id_comprobante y id_comprobante_original). Sin esto SQLAlchemy no puede
    # determinar cual es la FK de la relacion "padre → validaciones".
    comprobante: Mapped["Comprobante"] = relationship(  # noqa: F821
        back_populates="validaciones",
        foreign_keys="[Validacion.id_comprobante]",
    )

    __table_args__ = (
        CheckConstraint(
            f"clasificacion IN {CLASIFICACIONES_VALIDAS!r}",
            name="ck_validaciones_clasificacion",
        ),
        CheckConstraint(
            f"metodo_deteccion IN {METODOS_DETECCION_VALIDOS!r}",
            name="ck_validaciones_metodo_deteccion",
        ),
        CheckConstraint(
            "score_similitud IS NULL OR (score_similitud >= 0 AND score_similitud <= 1)",
            name="ck_validaciones_score_rango",
        ),
    )

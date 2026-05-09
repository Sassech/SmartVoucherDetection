"""Mixins reutilizables para modelos ORM.

`SoftDeleteMixin` agrega `deleted_at TIMESTAMPTZ NULL` segun D-06: las tablas
de negocio (Organizacion/Usuario/Comprobante/Validacion) requieren auditoria,
asi que no se borran fisicamente. `LogProcesamiento` queda hard delete (TTL).

NOTA: la PK UUID v7 y los timestamps de creacion (fecha_registro/fecha_validacion/
fecha_evento) NO se modelan como mixin porque sus nombres cambian segun la
entidad. Cada modelo los declara con su nombre semantico del ERD.
"""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Agrega `deleted_at` para soft delete.

    - `NULL` = registro activo
    - `NOT NULL` = registro borrado logicamente

    El indice acelera el filtro `WHERE deleted_at IS NULL` que aplica a casi
    toda lectura de negocio.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

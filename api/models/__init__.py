"""SQLAlchemy ORM models for SmartVoucherDetection.

Importar desde aqui asegura que todos los modelos esten registrados en
`Base.metadata` antes de que Alembic corra `--autogenerate`.
"""

from .comprobante import Comprobante
from .log_procesamiento import LogProcesamiento
from .organizacion import Organizacion
from .usuario import Usuario
from .validacion import Validacion

__all__ = [
    "Comprobante",
    "LogProcesamiento",
    "Organizacion",
    "Usuario",
    "Validacion",
]

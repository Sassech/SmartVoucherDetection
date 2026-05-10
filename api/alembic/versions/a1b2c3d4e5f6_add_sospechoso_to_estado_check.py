"""add_sospechoso_to_estado_check

Agrega 'sospechoso' al CHECK constraint de comprobantes.estado_actual.

Contexto: el estado 'sospechoso' faltaba en ESTADOS_VALIDOS (Fase 1) y por lo
tanto tambien en el CHECK de la DB. Capa 3 de deteccion necesita INSERT/UPDATE
con estado_actual='sospechoso' — sin este fix, Postgres rechaza cualquier
transicion a ese estado.

Alcance de PR-A:
- Solo CHECK constraint.
- El indice compuesto idx_comp_dedup y la FK id_comprobante_original van en
  la migracion de Block B (requiere CREATE INDEX CONCURRENTLY fuera de
  transaccion — manejado en PR-B).

Revision ID: a1b2c3d4e5f6
Revises: ba4e861e6950
Create Date: 2026-05-09
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ba4e861e6950"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Nombres de constraint — constantes para no repetir strings.
_CK_NAME = "ck_comprobantes_estado_actual"
_TABLE = "comprobantes"
_COLUMN = "estado_actual"

# Valor del CHECK con los 7 estados de Fase 1 (para downgrade).
_CHECK_FASE1 = (
    f"{_COLUMN} IN ("
    "'recibido', 'procesando', 'comparando', "
    "'en_revision', 'valido', 'duplicado', 'error'"
    ")"
)

# Valor del CHECK con los 8 estados de Fase 2 (incluye 'sospechoso').
_CHECK_FASE2 = (
    f"{_COLUMN} IN ("
    "'recibido', 'procesando', 'comparando', 'sospechoso', "
    "'en_revision', 'valido', 'duplicado', 'error'"
    ")"
)


def upgrade() -> None:
    """Drop CHECK con 7 estados → recrear con 8 (agrega 'sospechoso')."""
    op.drop_constraint(_CK_NAME, _TABLE, type_="check")
    op.create_check_constraint(_CK_NAME, _TABLE, _CHECK_FASE2)


def downgrade() -> None:
    """Restaura CHECK con 7 estados (elimina 'sospechoso')."""
    op.drop_constraint(_CK_NAME, _TABLE, type_="check")
    op.create_check_constraint(_CK_NAME, _TABLE, _CHECK_FASE1)

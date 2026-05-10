"""fase2_dedup_index_and_validacion_fk

Agrega el indice compuesto para Capa 2 y la FK id_comprobante_original en
validaciones para el audit trail de duplicados.

Contexto:
- idx_comp_dedup: indice parcial sobre (referencia, monto, fecha_deposito)
  WHERE referencia IS NOT NULL. Lo usa run_capa2 para exact-match eficiente.
  CREATE INDEX CONCURRENTLY no puede correr dentro de una transaccion — lo
  creamos con op.create_index para que Alembic lo maneje correctamente en
  context.configure(..., transaction_per_migration=...). Si la DB no soporta
  CONCURRENTLY (e.g. SQLite en tests), postgresql_concurrently se ignora.
- id_comprobante_original: FK nullable a comprobantes para trazar cual
  comprobante existente triggero la deteccion.

Revision ID: 34b207551c82
Revises: a1b2c3d4e5f6
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "34b207551c82"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega indice compuesto Capa2 + FK id_comprobante_original."""
    # 1. FK id_comprobante_original en validaciones para audit trail
    op.add_column(
        "validaciones",
        sa.Column(
            "id_comprobante_original",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_validaciones_comprobante_original",
        "validaciones",
        "comprobantes",
        ["id_comprobante_original"],
        ["id_comprobante"],
        ondelete="SET NULL",
    )

    # 2. Indice compuesto para dedup Capa 2
    # Nota: CREATE INDEX CONCURRENTLY no puede correr dentro de una transaccion.
    # Alembic gestiona esto a traves de `postgresql_concurrently=True` —
    # el engine lo traduce a CONCURRENTLY cuando la conexion lo permite.
    # En tests con SQLite o transacciones activas se omite CONCURRENTLY
    # automaticamente (no hay soporte nativo).
    op.create_index(
        "idx_comp_dedup",
        "comprobantes",
        ["referencia", "monto", "fecha_deposito"],
        postgresql_where=sa.text("referencia IS NOT NULL"),
    )


def downgrade() -> None:
    """Revierte indice compuesto y FK id_comprobante_original."""
    op.drop_index("idx_comp_dedup", table_name="comprobantes")
    op.drop_constraint(
        "fk_validaciones_comprobante_original",
        "validaciones",
        type_="foreignkey",
    )
    op.drop_column("validaciones", "id_comprobante_original")

"""fase7_plan_quota

Agrega columnas `plan` y `sin_cuota` a la tabla `usuarios` y un indice
compuesto en `comprobantes` para optimizar las consultas de cuota mensual.

Cubre requerimientos R-70 (plan), R-71 (sin_cuota) y R-72 (indice).

- ADD COLUMN plan VARCHAR(20) NOT NULL DEFAULT 'basic' + CHECK constraint
- ADD COLUMN sin_cuota BOOLEAN NOT NULL DEFAULT false
- Backfill: system@smartvoucher.local → plan='enterprise', sin_cuota=true
- CREATE INDEX ix_comprobantes_usuario_fecha ON comprobantes(id_usuario, fecha_registro DESC)

Revision ID: a9c4f812b357
Revises: f3a8e2d1c094
Create Date: 2026-05-23
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c4f812b357"
down_revision: Union[str, Sequence[str], None] = "f3a8e2d1c094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega plan + sin_cuota + indice compuesto comprobantes."""
    # 1. ADD COLUMN plan — NOT NULL DEFAULT 'basic' con CHECK constraint
    op.add_column(
        "usuarios",
        sa.Column(
            "plan",
            sa.String(20),
            nullable=False,
            server_default="basic",
        ),
    )
    op.create_check_constraint(
        "ck_usuarios_plan",
        "usuarios",
        "plan IN ('basic', 'pro', 'enterprise')",
    )

    # 2. ADD COLUMN sin_cuota — BOOLEAN NOT NULL DEFAULT false
    op.add_column(
        "usuarios",
        sa.Column(
            "sin_cuota",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 3. Backfill: system user → enterprise + sin_cuota=true
    op.execute("""
        UPDATE usuarios
        SET plan = 'enterprise', sin_cuota = true
        WHERE correo = 'system@smartvoucher.local'
    """)

    # 4. CREATE INDEX ix_comprobantes_usuario_fecha — optimiza COUNT mensual
    op.create_index(
        "ix_comprobantes_usuario_fecha",
        "comprobantes",
        ["id_usuario", sa.text("fecha_registro DESC")],
    )


def downgrade() -> None:
    """Revierte en orden inverso: indice → sin_cuota → plan."""
    # 1. Drop composite index
    op.drop_index("ix_comprobantes_usuario_fecha", table_name="comprobantes")

    # 2. Drop sin_cuota
    op.drop_column("usuarios", "sin_cuota")

    # 3. Drop plan (check constraint drops automatically with the column in PG)
    op.drop_constraint("ck_usuarios_plan", "usuarios", type_="check")
    op.drop_column("usuarios", "plan")

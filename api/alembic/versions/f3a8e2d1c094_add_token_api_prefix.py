"""add_token_api_prefix

Agrega columna `token_api_prefix VARCHAR(8) NULL` a `usuarios` con indice
para optimizar el pre-filtro de `require_api_key` (R-28, R-29, R-30).

La columna almacena los primeros 8 caracteres del `token_api_hash` (bcrypt)
para permitir un lookup indexado antes del costoso `bcrypt.checkpw` scan
completo. Con esto, `require_api_key` pasa de O(n) bcrypt ops a O(1).

Backfill: SET token_api_prefix = LEFT(token_api_hash, 8)
para todos los rows donde token_api_hash IS NOT NULL.

Revision ID: f3a8e2d1c094
Revises: 34b207551c82
Create Date: 2026-05-11
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8e2d1c094"
down_revision: Union[str, Sequence[str], None] = "34b207551c82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega token_api_prefix + indice + backfill."""
    # 1. Agregar columna nullable
    op.add_column(
        "usuarios",
        sa.Column("token_api_prefix", sa.String(8), nullable=True),
    )

    # 2. Crear indice B-tree para pre-filtro rapido
    op.create_index(
        "ix_usuarios_token_api_prefix",
        "usuarios",
        ["token_api_prefix"],
    )

    # 3. Backfill: tomar los primeros 8 chars del hash para rows existentes
    op.execute("""
        UPDATE usuarios
        SET token_api_prefix = LEFT(token_api_hash, 8)
        WHERE token_api_hash IS NOT NULL
    """)


def downgrade() -> None:
    """Revierte indice + columna (datos del backfill se pierden)."""
    op.drop_index("ix_usuarios_token_api_prefix", table_name="usuarios")
    op.drop_column("usuarios", "token_api_prefix")

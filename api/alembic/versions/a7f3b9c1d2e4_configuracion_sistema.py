"""configuracion_sistema — tabla clave/valor para pesos de scoring.

Crea la tabla `configuracion_sistema` con PK VARCHAR(64) y siembra los
4 pesos de scoring con valores por defecto. La siembra es idempotente via
ON CONFLICT DO NOTHING — se puede reaplicar sin errores.

Revision ID: a7f3b9c1d2e4
Revises: f3a8e2d1c094
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f3b9c1d2e4"
down_revision: Union[str, Sequence[str], None] = "f3a8e2d1c094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea tabla configuracion_sistema y siembra los 4 pesos de scoring."""
    op.create_table(
        "configuracion_sistema",
        sa.Column("key", sa.String(64), primary_key=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Siembra de los 4 pesos de scoring (idempotente via ON CONFLICT DO NOTHING).
    # PK es VARCHAR — no necesita CAST a uuid.
    _seed_weights = [
        ("scoring.w_ref", "0.35"),
        ("scoring.w_text", "0.30"),
        ("scoring.w_monto", "0.20"),
        ("scoring.w_fecha", "0.15"),
    ]

    for key, value in _seed_weights:
        op.execute(
            sa.text(
                """
                INSERT INTO configuracion_sistema (key, value, updated_at)
                VALUES (:key, :value, NOW())
                ON CONFLICT (key) DO NOTHING
                """
            ).bindparams(key=key, value=value)
        )


def downgrade() -> None:
    """Elimina la tabla configuracion_sistema completa."""
    op.drop_table("configuracion_sistema")

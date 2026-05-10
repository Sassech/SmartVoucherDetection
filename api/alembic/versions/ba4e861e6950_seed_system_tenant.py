"""seed_system_tenant — inserta la organizacion y usuario `system` para Fase 1.

Por que data migration y NO un script suelto:
- Alembic garantiza orden y atomicidad: el seed corre INMEDIATAMENTE despues
  de crear las tablas, en la misma transaccion logica del upgrade. Si falla,
  el `head` no avanza y la DB queda en estado consistente.
- Cualquier entorno (dev, CI, staging, prod) que llegue al `head` tiene el
  tenant garantizado. No hay "ah, falto correr el seed".
- Idempotencia: `ON CONFLICT DO NOTHING` permite reaplicar sin error.

UUIDs hardcoded vienen de `models/seed.py`. Si cambian alli, esta migracion
NO los va a actualizar (es un INSERT one-shot). Para cambiarlos hay que
escribir migracion nueva con UPDATE explicito.

Revision ID: ba4e861e6950
Revises: 607b4c53997b
Create Date: 2026-05-09 09:58:29.137371
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba4e861e6950"
down_revision: Union[str, Sequence[str], None] = "607b4c53997b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Constantes inline (NO importar desde `models.seed` para que la migracion
# sea autosuficiente: si un dia se borra/refactoriza ese modulo, esta
# migracion historica sigue corriendo. Las migraciones son inmutables).
_SYSTEM_ORG_ID = "019e0d75-323e-74b3-a249-90828e8673e6"
_SYSTEM_USER_ID = "019e0d75-323e-74b3-a249-909b3f77ee9f"
_SYSTEM_USER_PASSWORD_HASH = (
    "$2b$12$55kcgfnV37U7tBPMb9NgBe9DABmhO0Z7/ZaqHsmhVDLQNlFhqtZsm"
)


def upgrade() -> None:
    """Inserta organizacion + usuario `system` (idempotente).

    Casts explicitos `CAST(:id AS uuid)` porque asyncpg rechaza el coerce
    implicito de varchar→uuid (a diferencia de psycopg). NO usamos la sintaxis
    Postgres `:id::uuid` porque SQLAlchemy `text()` interpreta `::` como
    conflicto con su parser de bindparams.
    """
    op.execute(
        sa.text(
            """
            INSERT INTO organizaciones (
                id_organizacion, nombre, plan_suscripcion, fecha_registro
            )
            VALUES (
                CAST(:id AS uuid), :nombre, :plan, NOW()
            )
            ON CONFLICT (id_organizacion) DO NOTHING
            """
        ).bindparams(
            id=_SYSTEM_ORG_ID,
            nombre="system",
            plan="empresarial",
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO usuarios (
                id_usuario, id_organizacion, nombre, correo,
                contrasena_hash, rol, fecha_registro
            )
            VALUES (
                CAST(:id AS uuid), CAST(:org_id AS uuid), :nombre, :correo,
                :pwd_hash, :rol, NOW()
            )
            ON CONFLICT (id_usuario) DO NOTHING
            """
        ).bindparams(
            id=_SYSTEM_USER_ID,
            org_id=_SYSTEM_ORG_ID,
            nombre="system",
            correo="system@smartvoucher.local",
            pwd_hash=_SYSTEM_USER_PASSWORD_HASH,
            rol="admin",
        )
    )


def downgrade() -> None:
    """Elimina el seed.

    Solo borra si NO hay comprobantes asociados (FK con `ondelete=RESTRICT`
    se encarga). Si los hay, el downgrade falla y eso es deseable: el operador
    debe decidir explicitamente que hacer con esos datos antes de bajar la
    revision.
    """
    op.execute(
        sa.text("DELETE FROM usuarios WHERE id_usuario = CAST(:id AS uuid)").bindparams(
            id=_SYSTEM_USER_ID
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM organizaciones WHERE id_organizacion = CAST(:id AS uuid)"
        ).bindparams(id=_SYSTEM_ORG_ID)
    )

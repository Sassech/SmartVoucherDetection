"""Alembic env.py — async, lee DATABASE_URL desde api.config.settings.

Notas de diseno:
- `prepend_sys_path = .` en alembic.ini agrega `api/` a sys.path cuando
  Alembic corre desde `api/`, asi que `from config import settings`
  funciona sin trucos.
- `target_metadata` queda en None hasta Fase 1 (1.2.6); se llenara cuando
  existan los modelos ORM.
- El driver async (asyncpg) viene incrustado en DATABASE_URL desde `.env`.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from config import settings  # api/config.py — single source of truth

# Alembic Config object — accede al alembic.ini.
config = context.config

# Inyectamos la URL real desde settings; lo que hay en alembic.ini es solo
# un placeholder (`driver://user:pass@localhost/dbname`).
config.set_main_option("sqlalchemy.url", settings.database_url)

# Logging desde el .ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata de los modelos para autogenerate. Se conectara en Fase 1 (1.2.6).
# from models import Base  # noqa: ERA001
# target_metadata = Base.metadata  # noqa: ERA001
target_metadata = None


def run_migrations_offline() -> None:
    """Migraciones en modo offline (genera SQL sin conexion)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Crea engine async y corre migraciones contra la DB."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Migraciones en modo online (con conexion async real)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

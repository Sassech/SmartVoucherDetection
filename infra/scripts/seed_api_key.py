#!/usr/bin/env python3
"""One-time script: generate an API key and store its bcrypt hash in the system user.

Updates `usuarios.token_api_hash` for the user with email 'system@smartvoucher.local'.
The plaintext key is printed ONCE — save it immediately. It is never stored.

Usage (run from the api/ directory so database imports resolve):

    cd api && uv run python ../infra/scripts/seed_api_key.py

Requirements:
    - DATABASE_URL environment variable set (or .env present in project root).
    - The system user (system@smartvoucher.local) must exist in the database.
      Run Alembic migrations and the seed fixture first if starting fresh.

Exit codes:
    0 — key stored successfully.
    1 — user not found / no rows updated.
    2 — unexpected error.
"""

from __future__ import annotations

import asyncio
import secrets
import sys

import bcrypt
from sqlalchemy import text, update

# Ensure the api/ package is importable when invoked from repo root.
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))

from database import engine  # noqa: E402 — after sys.path fix
from models.seed import SYSTEM_USER_CORREO, SYSTEM_USER_ID  # noqa: E402
from models.usuario import Usuario  # noqa: E402


async def main() -> None:
    plain_key = secrets.token_urlsafe(32)
    hashed = bcrypt.hashpw(plain_key.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    async with engine.begin() as conn:
        # Update by ID (deterministic — SYSTEM_USER_ID never changes per seed.py).
        result = await conn.execute(
            update(Usuario)
            .where(Usuario.id_usuario == SYSTEM_USER_ID)
            .values(token_api_hash=hashed)
            .returning(text("1"))
        )
        rows_updated = result.rowcount

    if rows_updated == 0:
        print(
            f"\n❌  System user not found (id={SYSTEM_USER_ID}, email={SYSTEM_USER_CORREO}).",
            file=sys.stderr,
        )
        print("    Run Alembic migrations and seed the DB first.", file=sys.stderr)
        sys.exit(1)

    print(f"\n✅  API key stored for system user ({SYSTEM_USER_CORREO}).")
    print(f"🔑  Plaintext key (shown ONCE — save it now):\n\n   {plain_key}\n")


if __name__ == "__main__":
    asyncio.run(main())

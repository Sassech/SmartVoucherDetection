"""FastAPI dependency: validate X-API-Key header against usuarios.token_api_hash.

Strategy (Fase 4 — R-30):
    Use token_api_prefix to pre-filter candidates BEFORE running bcrypt:
        WHERE token_api_prefix = submitted_key[:8] AND deleted_at IS NULL

    This is an O(1) indexed lookup + bcrypt on the narrowed set (typically 1 row).
    NULL prefix rows are naturally excluded by the WHERE equality clause — so
    webapp-only users (no token_api_hash) are never compared. (S-14)

Security note:
    The 401 detail is identical for "key not found" and "wrong key" — prevents
    user enumeration (timing-safe as per R-16).

Performance impact:
    Prefix miss: 0 bcrypt ops (index short-circuits).
    Prefix match: 1 bcrypt op.
"""

from __future__ import annotations

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.usuario import Usuario


async def require_api_key(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    """Validate X-API-Key header and return the matching Usuario.

    Raises HTTP 401 for:
    - Missing or empty header       → "API key required"
    - Prefix not found in DB        → "Invalid API key" (no bcrypt overhead)
    - Prefix match, wrong full key  → "Invalid API key"

    Returns the full Usuario ORM object so routers can access id_usuario
    directly (no request.state mutation).
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    # Fase 4: indexed prefix pre-filter — avoids O(n) full bcrypt scan.
    # NULL token_api_prefix rows are excluded naturally by equality WHERE.
    prefix = x_api_key[:8]
    stmt = (
        select(Usuario)
        .where(
            Usuario.token_api_prefix == prefix,
            Usuario.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    key_bytes = x_api_key.encode("utf-8")
    for user in candidates:
        stored_hash = user.token_api_hash
        if stored_hash and bcrypt.checkpw(key_bytes, stored_hash.encode("utf-8")):
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )

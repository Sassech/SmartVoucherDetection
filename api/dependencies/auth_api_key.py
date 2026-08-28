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

The prefix-lookup + bcrypt verification itself lives in services.auth_helpers
(shared with auth_any.py — see sonarqube-final-hardening AD-02).
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.usuario import Usuario
from services.auth_helpers import authenticate_api_key


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

    return await authenticate_api_key(x_api_key, db)

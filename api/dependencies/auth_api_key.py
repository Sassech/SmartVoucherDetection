"""FastAPI dependency: validate X-API-Key header against usuarios.token_api_hash.

Strategy (Decision 2 from design doc):
    Iterate all active users with a stored hash (LIMIT 50) and perform
    bcrypt.checkpw() for each. O(n) per request — acceptable for Fase 3
    (≤ 50 users).

Scalability note (deferred to Fase 4):
    When user count exceeds ~200, add `token_api_prefix VARCHAR(8)` as an
    indexed column and pre-filter:
        WHERE token_api_prefix = :prefix AND deleted_at IS NULL
    before the bcrypt scan to avoid a full table scan on every request.

Security note:
    The 401 detail is identical for "key not found" and "wrong key" — this
    prevents user enumeration (timing-safe as per R-16).
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
    - Missing or empty header  → "API key required"
    - No bcrypt match found    → "Invalid API key"

    Returns the full Usuario ORM object so routers can access id_usuario
    directly (Decision 5: no request.state mutation).
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )

    # Fetch all active users with a token hash set.
    # LIMIT 50: acceptable for Fase 3. See scalability note above.
    stmt = (
        select(Usuario)
        .where(Usuario.deleted_at.is_(None))
        .where(Usuario.token_api_hash.is_not(None))
        .limit(50)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    key_bytes = x_api_key.encode("utf-8")
    for user in users:
        stored_hash = user.token_api_hash
        if stored_hash and bcrypt.checkpw(key_bytes, stored_hash.encode("utf-8")):
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )

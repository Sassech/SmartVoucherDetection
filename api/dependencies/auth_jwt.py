"""FastAPI dependency: validate Bearer JWT and return the authenticated Usuario.

Design (from fase-4-design.md):
- Reads Authorization: Bearer <token> via OAuth2PasswordBearer.
- Decodes/verifies via jwt_service.verify_token (raises 401 on failure).
- Loads Usuario from DB using `sub` claim (user UUID string).
- Raises 401 if user not found or has been soft-deleted.
- Does NOT touch require_api_key or any plugin route.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.usuario import Usuario
from services.jwt_service import verify_token

# OAuth2 scheme — reads Authorization: Bearer <token>.
# `auto_error=False` means we return None instead of a 403 for missing token,
# so we can return 401 (not 403) consistently.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/web/auth/login", auto_error=False)


async def require_jwt(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    """Validate Bearer token and return the authenticated Usuario.

    Raises:
        HTTPException(401): Missing, malformed, expired, or tampered token.
        HTTPException(401): User not found in DB or soft-deleted.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode and verify — raises 401 on any JWT error
    payload = verify_token(token)

    # Extract user ID from `sub` claim
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load from DB
    stmt = select(Usuario).where(
        Usuario.id_usuario == user_id,
        Usuario.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    usuario = result.scalar_one_or_none()

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return usuario

"""FastAPI dependency: validate Bearer JWT and return the authenticated Usuario.

Design (from fase-4-design.md):
- Reads Authorization: Bearer <token> via OAuth2PasswordBearer.
- Delegates verification + user lookup to services.auth_helpers.authenticate_bearer
  (shared with auth_any.py — see sonarqube-final-hardening AD-02).
- Raises 401 if user not found or has been soft-deleted.
- Does NOT touch require_api_key or any plugin route.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.usuario import Usuario
from services.auth_helpers import authenticate_bearer

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

    return await authenticate_bearer(f"Bearer {token}", db)

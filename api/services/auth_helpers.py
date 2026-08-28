"""Shared authentication helpers for X-API-Key and Bearer JWT validation.

Extracted from dependencies/auth_any.py, dependencies/auth_jwt.py, and
dependencies/auth_api_key.py to eliminate duplication (sonarqube-final-hardening
AD-02): duplicated_lines_density was auth_any 39.4%, auth_jwt 39.3%,
auth_api_key 25.4% before this extraction.

Each dependencies/auth_*.py module keeps its own FastAPI signature (Header /
Depends injection) and pre-condition checks (missing header messages), then
delegates the actual DB lookup + credential verification to the pure async
functions below. HTTP error semantics (status codes, detail messages,
WWW-Authenticate headers) are unchanged from the pre-refactor implementation.
"""

from __future__ import annotations

import uuid

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.usuario import Usuario
from services.jwt_service import verify_token


async def authenticate_api_key(x_api_key: str, db: AsyncSession) -> Usuario:
    """Validate an X-API-Key value against usuarios.token_api_hash.

    Uses token_api_prefix to pre-filter candidates before running bcrypt
    (O(1) indexed lookup + bcrypt only on the narrowed set, typically 1 row).
    NULL prefix rows are naturally excluded by the WHERE equality clause.

    Raises HTTP 401 "Invalid API key" for both "prefix not found" and
    "prefix match, wrong key" — identical detail prevents user enumeration
    (timing-safe, R-16).
    """
    prefix = x_api_key[:8]
    stmt = select(Usuario).where(
        Usuario.token_api_prefix == prefix,
        Usuario.deleted_at.is_(None),
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


async def authenticate_bearer(auth_header: str, db: AsyncSession) -> Usuario:
    """Validate an "Authorization: Bearer <token>" header and return the Usuario.

    Strips the "Bearer " prefix, decodes/verifies via jwt_service.verify_token,
    loads the user from the `sub` claim, and raises HTTP 401 for any invalid
    token, payload, subject, or missing/soft-deleted user.
    """
    token = auth_header[len("Bearer ") :]
    try:
        payload = verify_token(token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

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

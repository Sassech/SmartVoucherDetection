"""FastAPI dependency: accept Bearer JWT OR X-API-Key — whichever is present.

Used by upload endpoints so both:
  - API integrations (X-API-Key)
  - Webapp users (Bearer JWT cookie-backed token)
can upload comprobantes without duplicating endpoint logic.

Resolution order:
  1. X-API-Key header present → validate via require_api_key logic
  2. Authorization: Bearer present → validate via require_jwt logic
  3. Neither → HTTP 401
"""

from __future__ import annotations

import uuid

import bcrypt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.usuario import Usuario
from services.jwt_service import verify_token


async def require_user(
    request: Request,
    x_api_key: str = Header(default="", alias="X-API-Key"),
    db: AsyncSession = Depends(get_session),
) -> Usuario:
    """Return the authenticated Usuario from X-API-Key or Bearer JWT.

    Raises HTTP 401 if neither credential is valid.
    """
    # ── 1. Try API key first ──────────────────────────────────────────────────
    if x_api_key:
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

    # ── 2. Try Bearer JWT ─────────────────────────────────────────────────────
    auth_header: str = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
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

    # ── 3. Nothing provided ───────────────────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide X-API-Key or Bearer token",
    )

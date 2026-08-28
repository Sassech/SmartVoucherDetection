"""FastAPI dependency: accept Bearer JWT OR X-API-Key — whichever is present.

Used by upload endpoints so both:
  - API integrations (X-API-Key)
  - Webapp users (Bearer JWT cookie-backed token)
can upload comprobantes without duplicating endpoint logic.

Resolution order:
  1. X-API-Key header present → validate via require_api_key logic
  2. Authorization: Bearer present → validate via require_jwt logic
  3. Neither → HTTP 401

Credential verification itself lives in services.auth_helpers (shared with
auth_jwt.py / auth_api_key.py — see sonarqube-final-hardening AD-02).
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.usuario import Usuario
from services.auth_helpers import authenticate_api_key, authenticate_bearer

# Re-exported under their historical private names for import stability —
# existing callers/tests importing `_authenticate_api_key` /
# `_authenticate_bearer` from this module keep working unchanged.
_authenticate_api_key = authenticate_api_key
_authenticate_bearer = authenticate_bearer


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
        return await _authenticate_api_key(x_api_key, db)

    # ── 2. Try Bearer JWT ─────────────────────────────────────────────────────
    auth_header: str = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return await _authenticate_bearer(auth_header, db)

    # ── 3. Nothing provided ───────────────────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide X-API-Key or Bearer token",
    )

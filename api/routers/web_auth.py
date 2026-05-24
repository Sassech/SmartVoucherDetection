"""Router: POST /web/auth/login, /refresh, /logout — GET /web/auth/me.

Covers:
  R-21 (login), R-22 (refresh), R-23 (logout), R-24 (me)
  R-75 (register), R-76 (api-key generate), R-77 (api-key revoke), R-78 (api-key status)

Design decisions (fase-4-design.md + fase-7-design.md):
- Login sets BOTH access_token (HttpOnly, 15min) and refresh_token (HttpOnly, 7d) cookies.
- Refresh uses atomic rotate_jti (GETDEL + SET) — prevents replay on concurrent calls.
- Login runs dummy bcrypt when user not found — prevents timing oracle (S-03).
- Logout requires valid Bearer token (require_jwt) before invalidating JTI.
- /me returns UsuarioPublic (no sensitive fields).
- /register creates user with plan='basic', sin_cuota=False, rol='operador' (R-75).
- /api-key (POST) generates 32-byte URL-safe token, stores prefix+bcrypt hash (R-76).
- /api-key (DELETE) nullifies prefix+hash (R-77).
- /api-key/status (GET) returns {has_key, prefix} without exposing hash (R-78).
- All endpoints under /web/auth prefix; login/refresh skip require_jwt explicitly.
"""

from __future__ import annotations

import secrets
import uuid

import bcrypt
import redis.asyncio as aioredis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_redis, get_session
from dependencies.auth_jwt import require_jwt
from models.usuario import Usuario
from schemas.auth import (
    ApiKeyResponse,
    ApiKeyStatus,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UsuarioPublic,
    UsuarioWithPlan,
)
from services.jwt_service import (
    create_access_token,
    create_refresh_token,
    is_jti_valid,
    revoke_jti,
    rotate_jti,
    store_jti,
)

router = APIRouter(prefix="/web/auth", tags=["web-auth"])

# Cookie settings (Fase 4 — R-21/R-22)
_ACCESS_COOKIE_MAX_AGE = 15 * 60   # 15 minutes in seconds
_REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

# A pre-computed dummy bcrypt hash for timing-safe S-03.
# Using cost=4 so tests don't time out; production can raise this.
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=4)).decode()


# ---------------------------------------------------------------------------
# Internal helpers — extracted for testability (pure-ish functions)
# ---------------------------------------------------------------------------


async def _get_user_by_email(email: str, db: AsyncSession) -> Usuario | None:
    """Load a Usuario by correo (non-deleted). Returns None if not found."""
    stmt = select(Usuario).where(
        Usuario.correo == email,
        Usuario.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_user_by_id(user_id: uuid.UUID, db: AsyncSession) -> Usuario | None:
    """Load a Usuario by id (non-deleted). Returns None if not found."""
    stmt = select(Usuario).where(
        Usuario.id_usuario == user_id,
        Usuario.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_jti: str,
) -> None:
    """Set both HttpOnly cookies on the response."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_ACCESS_COOKIE_MAX_AGE,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_jti,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_REFRESH_COOKIE_MAX_AGE,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear both auth cookies (Max-Age=0)."""
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=0,
    )
    response.set_cookie(
        key="refresh_token",
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=0,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    """POST /web/auth/login — validate credentials, issue JWT pair.

    Timing-safe: runs dummy bcrypt even when user not found (S-03).
    Sets both access_token and refresh_token as HttpOnly cookies (OQ-1 resolved).
    """
    user = await _get_user_by_email(body.correo, db)

    if user is not None:
        # Real bcrypt check
        password_matches = bcrypt.checkpw(
            body.contrasena.encode("utf-8"),
            user.contrasena_hash.encode("utf-8"),
        )
    else:
        # Timing-safe: run dummy bcrypt to prevent user enumeration via latency
        bcrypt.checkpw(b"dummy", _DUMMY_HASH.encode("utf-8"))
        password_matches = False

    if not password_matches or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Issue token pair
    refresh_jti = create_refresh_token()
    access_token = create_access_token(
        sub=str(user.id_usuario),
        org=str(user.id_organizacion),
        rol=user.rol,
        jti=refresh_jti,
    )

    await store_jti(redis, refresh_jti, str(user.id_usuario))
    _set_auth_cookies(response, access_token, refresh_jti)

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    """POST /web/auth/refresh — rotate token pair.

    Reads refresh_token cookie, validates JTI in Redis, issues new pair.
    Old JTI is atomically consumed (GETDEL + SET) — prevents replay (S-06).
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    # Validate old JTI exists in Redis
    if not await is_jti_valid(redis, refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Look up user_id stored under old JTI
    user_id_str = await redis.get(f"jti:{refresh_token}")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Load user from DB
    user = await _get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Atomically rotate JTI
    new_jti = create_refresh_token()
    rotated = await rotate_jti(redis, refresh_token, new_jti, str(user_id))
    if not rotated:
        # Race condition: another request consumed the JTI first
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Issue new access token
    new_access_token = create_access_token(
        sub=str(user.id_usuario),
        org=str(user.id_organizacion),
        rol=user.rol,
        jti=new_jti,
    )

    _set_auth_cookies(response, new_access_token, new_jti)

    return TokenResponse(access_token=new_access_token)


@router.post("/logout", status_code=200)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    usuario: Usuario = Depends(require_jwt),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """POST /web/auth/logout — invalidate JTI, clear cookies.

    Requires valid Bearer access token. Revokes refresh JTI from Redis.
    Clears both auth cookies via Max-Age=0.
    """
    if refresh_token:
        await revoke_jti(redis, refresh_token)

    _clear_auth_cookies(response)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UsuarioPublic)
async def me(usuario: Usuario = Depends(require_jwt)) -> UsuarioPublic:
    """GET /web/auth/me — return public user info for authenticated user."""
    return UsuarioPublic.model_validate(usuario)


# ---------------------------------------------------------------------------
# Fase 7 — Multi-user: register + API key endpoints (R-75/R-76/R-77/R-78)
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UsuarioWithPlan, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_session),
) -> UsuarioWithPlan:
    """POST /web/auth/register — crear nuevo usuario con plan=basic (R-75).

    Valida unicidad de email (409 si ya existe). Hashea password con bcrypt.
    Retorna 201 con {id_usuario, correo, nombre, rol, plan}. Sin JWT.
    """
    # Check email uniqueness
    existing = await _get_user_by_email(body.correo, db)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash password with bcrypt
    hashed = bcrypt.hashpw(body.contrasena.encode("utf-8"), bcrypt.gensalt()).decode()

    # New users are assigned to the system org (SYSTEM_ORG_ID).
    # Multi-tenant org selection is deferred to a future phase.
    from models.seed import SYSTEM_ORG_ID  # noqa: PLC0415

    new_user = Usuario(
        nombre=body.nombre,
        correo=str(body.correo),
        contrasena_hash=hashed,
        rol="operador",
        plan="basic",
        sin_cuota=False,
        id_organizacion=SYSTEM_ORG_ID,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UsuarioWithPlan.model_validate(new_user)


@router.post(
    "/api-key",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_api_key(
    usuario: Usuario = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> ApiKeyResponse:
    """POST /web/auth/api-key — generar (o regenerar) API key para usuario JWT (R-76).

    Genera token_urlsafe(32), guarda prefix[:8] y bcrypt hash.
    Sobreescribe cualquier key anterior. Retorna plaintext UNA vez.
    """
    plain_key = secrets.token_urlsafe(32)
    prefix = plain_key[:8]
    hashed = bcrypt.hashpw(plain_key.encode("utf-8"), bcrypt.gensalt()).decode()

    usuario.token_api_prefix = prefix
    usuario.token_api_hash = hashed
    await db.commit()

    return ApiKeyResponse(
        api_key=plain_key,
        message="API key generated. Store it securely — it will not be shown again.",
    )


@router.delete("/api-key", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    usuario: Usuario = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """DELETE /web/auth/api-key — revocar API key del usuario autenticado (R-77).

    Nullifica token_api_hash y token_api_prefix.
    """
    usuario.token_api_hash = None
    usuario.token_api_prefix = None
    await db.commit()

    return {"message": "API key revoked."}


@router.get("/api-key/status", response_model=ApiKeyStatus)
async def api_key_status(
    usuario: Usuario = Depends(require_jwt),
) -> ApiKeyStatus:
    """GET /web/auth/api-key/status — estado del API key sin exponer hash (R-78).

    Retorna {has_key: bool, prefix: str|null}.
    """
    has_key = usuario.token_api_prefix is not None
    return ApiKeyStatus(
        has_key=has_key,
        prefix=usuario.token_api_prefix,
    )

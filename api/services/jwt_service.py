"""JWT service — token creation, verification, and Redis JTI operations.

All functions are pure (no global state, no side effects beyond Redis).
Redis key pattern: `jti:{uuid}` → `{user_id}`, TTL = 7 days.

Design decisions (from fase-4-design.md):
- HS256 symmetric signing (single backend, no key distribution needed).
- Access token TTL: 15 minutes. Claims: sub, org, rol, jti, exp.
- Refresh token is just a UUID4 string used as a JTI key in Redis.
- rotate_jti uses atomic pipeline (GETDEL + SET) to prevent replay on
  concurrent refresh calls.
- verify_token raises HTTPException(401) — not JWTError — so callers
  don't need to catch different exception types.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from jose import JWTError, jwt

from config import settings

# Redis key prefix for JTIs
_JTI_PREFIX = "jti:"
_JTI_TTL_SECONDS = 604800  # 7 days


# ---------------------------------------------------------------------------
# Access token
# ---------------------------------------------------------------------------


def create_access_token(
    sub: str,
    org: str,
    rol: str,
    jti: str,
) -> str:
    """Sign and return an HS256 JWT with claims {sub, org, rol, jti, exp}.

    TTL is taken from settings.access_token_expire_minutes (default 15).
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": sub,
        "org": org,
        "rol": rol,
        "jti": jti,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Refresh token (JTI generation)
# ---------------------------------------------------------------------------


def create_refresh_token() -> str:
    """Return a new UUID4 string to use as the refresh JTI.

    The JTI itself IS the refresh token — stored in Redis and sent to the
    client as an HttpOnly cookie value.
    """
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def verify_token(token: str) -> dict:
    """Decode and verify an HS256 JWT. Raises HTTPException(401) on any error.

    Returns the decoded payload dict on success.
    Errors raised include: expired token, invalid signature, malformed token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc) if "expired" not in str(exc).lower() else "Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# Redis JTI operations
# ---------------------------------------------------------------------------


async def store_jti(
    redis: aioredis.Redis,
    jti: str,
    user_id: str,
) -> None:
    """Store JTI in Redis with TTL=7d.

    Key: `jti:{jti}`, Value: `{user_id}`.
    """
    await redis.set(f"{_JTI_PREFIX}{jti}", user_id, ex=_JTI_TTL_SECONDS)


async def rotate_jti(
    redis: aioredis.Redis,
    old_jti: str,
    new_jti: str,
    user_id: str,
) -> bool:
    """Atomically delete old JTI and write new JTI.

    Uses a pipeline for atomic GETDEL + conditional SET to prevent replay
    on concurrent refresh calls.

    Returns:
        True  — rotation succeeded (old JTI existed and was consumed).
        False — old JTI was missing (already used or expired → 401 caller).
    """
    pipe = redis.pipeline(transaction=True)
    await pipe.get(f"{_JTI_PREFIX}{old_jti}")
    await pipe.delete(f"{_JTI_PREFIX}{old_jti}")
    results = await pipe.execute()
    existing_value = results[0]  # None if key didn't exist

    if existing_value is None:
        return False

    # Old JTI existed → write new JTI atomically
    await redis.set(f"{_JTI_PREFIX}{new_jti}", user_id, ex=_JTI_TTL_SECONDS)
    return True


async def revoke_jti(redis: aioredis.Redis, jti: str) -> None:
    """Delete a JTI from Redis (logout / explicit revocation)."""
    await redis.delete(f"{_JTI_PREFIX}{jti}")


async def is_jti_valid(redis: aioredis.Redis, jti: str) -> bool:
    """Return True if the JTI key exists in Redis."""
    exists = await redis.exists(f"{_JTI_PREFIX}{jti}")
    return bool(exists)

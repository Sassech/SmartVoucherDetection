"""Unit tests for jwt_service — all pure-function and Redis-backed behavior.

TDD cycle: these tests were written BEFORE the implementation exists.
Uses fakeredis for Redis operations.
"""

from __future__ import annotations

import time
import uuid

import fakeredis
import pytest
from jose import jwt

from config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_redis() -> fakeredis.FakeRedis:
    """Return a synchronous FakeRedis instance."""
    return fakeredis.FakeRedis(decode_responses=True)


async def _make_async_fake_redis() -> fakeredis.aioredis.FakeRedis:
    """Return an async FakeRedis instance."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    """Tests for jwt_service.create_access_token."""

    def test_returns_valid_jwt_string(self):
        """Token must be a decodable HS256 JWT string."""
        from services.jwt_service import create_access_token

        token = create_access_token(
            sub="user-123",
            org="org-456",
            rol="operador",
            jti="jti-abc",
        )
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # header.payload.signature

    def test_claims_are_correct(self):
        """Decoded payload must contain correct sub, org, rol, jti claims."""
        from services.jwt_service import create_access_token

        jti = str(uuid.uuid4())
        token = create_access_token(
            sub="user-999",
            org="org-111",
            rol="admin",
            jti=jti,
        )
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        assert payload["sub"] == "user-999"
        assert payload["org"] == "org-111"
        assert payload["rol"] == "admin"
        assert payload["jti"] == jti

    def test_token_expires_in_15_minutes(self):
        """Token exp claim must be ~15 minutes from now."""
        from services.jwt_service import create_access_token

        token = create_access_token(
            sub="u",
            org="o",
            rol="operador",
            jti="j",
        )
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        now = int(time.time())
        assert payload["exp"] > now
        # Expire within 15 minutes + 5 seconds buffer
        assert payload["exp"] <= now + 15 * 60 + 5


# ---------------------------------------------------------------------------
# create_refresh_token (returns UUID string)
# ---------------------------------------------------------------------------


class TestCreateRefreshToken:
    """Tests for jwt_service.create_refresh_token."""

    def test_returns_uuid_string(self):
        """create_refresh_token must return a UUID4 string."""
        from services.jwt_service import create_refresh_token

        jti = create_refresh_token()
        assert isinstance(jti, str)
        # Must be valid UUID
        parsed = uuid.UUID(jti)
        assert parsed.version == 4

    def test_each_call_returns_unique_jti(self):
        """Each call must generate a different JTI (no hardcoded value)."""
        from services.jwt_service import create_refresh_token

        jti1 = create_refresh_token()
        jti2 = create_refresh_token()
        assert jti1 != jti2


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------


class TestVerifyToken:
    """Tests for jwt_service.verify_token."""

    def test_valid_token_returns_payload(self):
        """verify_token must return the decoded payload for a valid token."""
        from services.jwt_service import create_access_token, verify_token

        token = create_access_token(
            sub="user-1",
            org="org-1",
            rol="operador",
            jti="test-jti",
        )
        payload = verify_token(token)
        assert payload["sub"] == "user-1"
        assert payload["jti"] == "test-jti"

    def test_tampered_token_raises_401(self):
        """Tampered token must raise HTTPException 401."""
        from fastapi import HTTPException

        from services.jwt_service import verify_token

        # Sign with a different secret → tampered
        tampered = jwt.encode(
            {"sub": "hacker"},
            "wrong-secret",
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered)
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        """Expired token must raise HTTPException 401."""
        from fastapi import HTTPException
        from jose import jwt as jose_jwt

        from services.jwt_service import verify_token

        # Create token that expired 1 second ago
        expired_payload = {
            "sub": "u",
            "org": "o",
            "rol": "r",
            "jti": "j",
            "exp": int(time.time()) - 1,
        }
        expired_token = jose_jwt.encode(
            expired_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# store_jti, is_jti_valid, revoke_jti (async Redis ops)
# ---------------------------------------------------------------------------


class TestJtiRedisOps:
    """Tests for store_jti, is_jti_valid, revoke_jti."""

    @pytest.mark.asyncio
    async def test_store_jti_then_is_valid(self):
        """Stored JTI must be reported as valid."""
        from services.jwt_service import is_jti_valid, store_jti

        redis = await _make_async_fake_redis()
        jti = str(uuid.uuid4())
        await store_jti(redis, jti, "user-42")
        assert await is_jti_valid(redis, jti) is True

    @pytest.mark.asyncio
    async def test_unknown_jti_is_not_valid(self):
        """JTI that was never stored must not be valid."""
        from services.jwt_service import is_jti_valid

        redis = await _make_async_fake_redis()
        assert await is_jti_valid(redis, "nonexistent-jti") is False

    @pytest.mark.asyncio
    async def test_revoke_jti_makes_it_invalid(self):
        """Revoked JTI must not be valid afterwards."""
        from services.jwt_service import is_jti_valid, revoke_jti, store_jti

        redis = await _make_async_fake_redis()
        jti = str(uuid.uuid4())
        await store_jti(redis, jti, "user-7")
        await revoke_jti(redis, jti)
        assert await is_jti_valid(redis, jti) is False

    @pytest.mark.asyncio
    async def test_store_jti_sets_correct_ttl(self):
        """Stored JTI must have TTL close to 7 days."""
        from services.jwt_service import store_jti

        redis = await _make_async_fake_redis()
        jti = str(uuid.uuid4())
        await store_jti(redis, jti, "user-1")
        ttl = await redis.ttl(f"jti:{jti}")
        # TTL should be 7 days = 604800 seconds, allow 5s buffer
        assert 604795 <= ttl <= 604800


# ---------------------------------------------------------------------------
# rotate_jti (atomic JTI rotation)
# ---------------------------------------------------------------------------


class TestRotateJti:
    """Tests for rotate_jti — atomic GETDEL + SET."""

    @pytest.mark.asyncio
    async def test_rotate_valid_jti_returns_true(self):
        """rotate_jti with an existing JTI must return True."""
        from services.jwt_service import rotate_jti, store_jti

        redis = await _make_async_fake_redis()
        old_jti = str(uuid.uuid4())
        new_jti = str(uuid.uuid4())
        await store_jti(redis, old_jti, "user-5")
        result = await rotate_jti(redis, old_jti, new_jti, "user-5")
        assert result is True

    @pytest.mark.asyncio
    async def test_rotate_deletes_old_jti(self):
        """After rotation, old JTI must not be valid."""
        from services.jwt_service import is_jti_valid, rotate_jti, store_jti

        redis = await _make_async_fake_redis()
        old_jti = str(uuid.uuid4())
        new_jti = str(uuid.uuid4())
        await store_jti(redis, old_jti, "user-5")
        await rotate_jti(redis, old_jti, new_jti, "user-5")
        assert await is_jti_valid(redis, old_jti) is False

    @pytest.mark.asyncio
    async def test_rotate_creates_new_jti(self):
        """After rotation, new JTI must be valid."""
        from services.jwt_service import is_jti_valid, rotate_jti, store_jti

        redis = await _make_async_fake_redis()
        old_jti = str(uuid.uuid4())
        new_jti = str(uuid.uuid4())
        await store_jti(redis, old_jti, "user-5")
        await rotate_jti(redis, old_jti, new_jti, "user-5")
        assert await is_jti_valid(redis, new_jti) is True

    @pytest.mark.asyncio
    async def test_rotate_missing_jti_returns_false(self):
        """rotate_jti with non-existent old JTI must return False."""
        from services.jwt_service import rotate_jti

        redis = await _make_async_fake_redis()
        result = await rotate_jti(redis, "nonexistent", "new-jti", "user-5")
        assert result is False

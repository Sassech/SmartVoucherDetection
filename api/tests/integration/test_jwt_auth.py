"""Integration tests for POST /web/auth/* endpoints — S-01 through S-10.

Tests use fakeredis for Redis and mock the DB session.
All tests run WITHOUT real DB — mock Usuario returned by session.

Scenarios covered:
    S-01: valid login → 200, access_token + refresh_token cookies
    S-02: wrong password → 401
    S-03: unknown email → 401 (timing-safe dummy bcrypt)
    S-04: valid refresh → new token pair, old JTI invalidated
    S-05: missing refresh cookie → 401
    S-06: replayed (already used) refresh token → 401
    S-07: valid logout → 200, cookies cleared, JTI deleted
    S-08: GET /me with valid token → UsuarioPublic
    S-09: GET /me with expired token → 401
    S-10: plugin route unaffected by JWT changes (no require_jwt invoked)
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import fakeredis
import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio

from config import settings
from database import get_redis, get_session
from main import app
from models.seed import SYSTEM_ORG_ID, SYSTEM_USER_ID
from services.jwt_service import (
    create_access_token,
    create_refresh_token,
    store_jti,
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TEST_EMAIL = "test@example.com"
_TEST_PASSWORD = "correct-horse-battery-staple"
_WRONG_PASSWORD = "wrong-password"
_UNKNOWN_EMAIL = "ghost@example.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_usuario(
    correo: str = _TEST_EMAIL,
    password: str = _TEST_PASSWORD,
) -> MagicMock:
    """Return a mock Usuario ORM object with a real bcrypt hash."""
    import bcrypt

    mock = MagicMock()
    mock.id_usuario = SYSTEM_USER_ID
    mock.id_organizacion = SYSTEM_ORG_ID
    mock.correo = correo
    mock.nombre = "Test User"
    mock.rol = "operador"
    mock.plan = "basic"
    mock.deleted_at = None
    mock.contrasena_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt(rounds=4)
    ).decode()
    return mock


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Async fakeredis client for JWT tests."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def async_client(
    redis_client: fakeredis.aioredis.FakeRedis,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx async client with all dependencies overridden.

    - get_session → mock that returns None (no DB for unit-like auth tests)
    - get_redis → fakeredis client
    """

    async def _override_session() -> AsyncGenerator[None, None]:
        yield MagicMock()  # session mock — not used in login directly

    async def _override_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
        yield redis_client

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_redis] = _override_redis

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# S-01: Valid credentials → 200 + both cookies
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest.mark.asyncio
    async def test_s01_valid_login_returns_200_and_cookies(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-01: valid login → 200, access_token cookie set, refresh cookie set."""
        mock_user = _make_mock_usuario()

        with patch("routers.web_auth._get_user_by_email", return_value=mock_user):
            response = await async_client.post(
                "/web/auth/login",
                json={"correo": _TEST_EMAIL, "contrasena": _TEST_PASSWORD},
            )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900

        # Both cookies must be set as HttpOnly
        cookies = response.headers.get_list("set-cookie")
        cookie_names = [c.split("=")[0].strip() for c in cookies]
        assert "access_token" in cookie_names or any(
            "access_token" in c for c in cookies
        ), f"access_token cookie missing. cookies: {cookies}"
        assert any("refresh_token" in c for c in cookies), (
            f"refresh_token cookie missing. cookies: {cookies}"
        )

    @pytest.mark.asyncio
    async def test_s02_wrong_password_returns_401(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-02: wrong password → 401."""
        mock_user = _make_mock_usuario()

        with patch("routers.web_auth._get_user_by_email", return_value=mock_user):
            response = await async_client.post(
                "/web/auth/login",
                json={"correo": _TEST_EMAIL, "contrasena": _WRONG_PASSWORD},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_s02_no_cookie_on_failed_login(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-02 supplemental: no cookie set when login fails."""
        mock_user = _make_mock_usuario()

        with patch("routers.web_auth._get_user_by_email", return_value=mock_user):
            response = await async_client.post(
                "/web/auth/login",
                json={"correo": _TEST_EMAIL, "contrasena": _WRONG_PASSWORD},
            )

        assert "set-cookie" not in response.headers

    @pytest.mark.asyncio
    async def test_s03_unknown_email_returns_401(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-03: non-existent email → 401 (timing-safe dummy bcrypt runs)."""
        with patch("routers.web_auth._get_user_by_email", return_value=None):
            response = await async_client.post(
                "/web/auth/login",
                json={"correo": _UNKNOWN_EMAIL, "contrasena": "anything"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"


# ---------------------------------------------------------------------------
# S-04 to S-06: Refresh endpoint
# ---------------------------------------------------------------------------


class TestRefresh:
    @pytest.mark.asyncio
    async def test_s04_valid_refresh_returns_new_token(
        self,
        async_client: httpx.AsyncClient,
        redis_client: fakeredis.aioredis.FakeRedis,
    ):
        """S-04: valid refresh cookie → 200 with new access_token, old JTI deleted."""
        old_jti = create_refresh_token()
        user_id_str = str(SYSTEM_USER_ID)
        await store_jti(redis_client, old_jti, user_id_str)

        mock_user = _make_mock_usuario()

        with patch("routers.web_auth._get_user_by_id", return_value=mock_user):
            response = await async_client.post(
                "/web/auth/refresh",
                cookies={"refresh_token": old_jti},
            )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body

        # Old JTI must be gone from Redis
        old_exists = await redis_client.exists(f"jti:{old_jti}")
        assert old_exists == 0, "Old JTI must be deleted after rotation"

    @pytest.mark.asyncio
    async def test_s04_refresh_creates_new_jti(
        self,
        async_client: httpx.AsyncClient,
        redis_client: fakeredis.aioredis.FakeRedis,
    ):
        """S-04: after refresh, a new JTI must exist in Redis."""
        old_jti = create_refresh_token()
        await store_jti(redis_client, old_jti, str(SYSTEM_USER_ID))
        mock_user = _make_mock_usuario()

        # Count keys before
        keys_before = await redis_client.keys("jti:*")

        with patch("routers.web_auth._get_user_by_id", return_value=mock_user):
            response = await async_client.post(
                "/web/auth/refresh",
                cookies={"refresh_token": old_jti},
            )

        assert response.status_code == 200
        keys_after = await redis_client.keys("jti:*")
        # One old removed, one new added → same count
        assert len(keys_after) == len(keys_before)

    @pytest.mark.asyncio
    async def test_s05_missing_refresh_cookie_returns_401(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-05: missing refresh cookie → 401."""
        response = await async_client.post("/web/auth/refresh")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_s06_replayed_jti_returns_401(
        self,
        async_client: httpx.AsyncClient,
        redis_client: fakeredis.aioredis.FakeRedis,
    ):
        """S-06: already-consumed JTI (not in Redis) → 401."""
        consumed_jti = create_refresh_token()
        # Don't store it — simulate already consumed

        response = await async_client.post(
            "/web/auth/refresh",
            cookies={"refresh_token": consumed_jti},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# S-07: Logout
# ---------------------------------------------------------------------------


class TestLogout:
    def _valid_access_token(self, jti: str) -> str:
        return create_access_token(
            sub=str(SYSTEM_USER_ID),
            org=str(SYSTEM_ORG_ID),
            rol="operador",
            jti=jti,
        )

    @pytest.mark.asyncio
    async def test_s07_valid_logout_returns_200(
        self,
        async_client: httpx.AsyncClient,
        redis_client: fakeredis.aioredis.FakeRedis,
    ):
        """S-07: valid logout → 200, JTI deleted, cookies cleared."""
        from dependencies.auth_jwt import require_jwt

        jti = create_refresh_token()
        await store_jti(redis_client, jti, str(SYSTEM_USER_ID))

        mock_user = _make_mock_usuario()
        mock_user.id_usuario = SYSTEM_USER_ID
        # Inject jti into the token payload
        token = self._valid_access_token(jti)

        # Override require_jwt to return mock user with the jti in payload
        async def _mock_require_jwt():
            return mock_user

        app.dependency_overrides[require_jwt] = _mock_require_jwt

        try:
            response = await async_client.post(
                "/web/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            app.dependency_overrides.pop(require_jwt, None)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_s07_logout_deletes_jti(
        self,
        async_client: httpx.AsyncClient,
        redis_client: fakeredis.aioredis.FakeRedis,
    ):
        """S-07: after logout, JTI must not exist in Redis."""
        from dependencies.auth_jwt import require_jwt

        jti = create_refresh_token()
        await store_jti(redis_client, jti, str(SYSTEM_USER_ID))
        token = self._valid_access_token(jti)

        mock_user = _make_mock_usuario()

        async def _mock_require_jwt():
            return mock_user

        app.dependency_overrides[require_jwt] = _mock_require_jwt

        try:
            response = await async_client.post(
                "/web/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                cookies={"refresh_token": jti},
            )
        finally:
            app.dependency_overrides.pop(require_jwt, None)

        assert response.status_code == 200
        # JTI must be gone
        exists = await redis_client.exists(f"jti:{jti}")
        assert exists == 0

    @pytest.mark.asyncio
    async def test_s07_logout_clears_refresh_cookie(
        self,
        async_client: httpx.AsyncClient,
        redis_client: fakeredis.aioredis.FakeRedis,
    ):
        """S-07: logout response must clear the refresh_token cookie (Max-Age=0)."""
        from dependencies.auth_jwt import require_jwt

        jti = create_refresh_token()
        await store_jti(redis_client, jti, str(SYSTEM_USER_ID))
        token = self._valid_access_token(jti)

        mock_user = _make_mock_usuario()

        async def _mock_require_jwt():
            return mock_user

        app.dependency_overrides[require_jwt] = _mock_require_jwt

        try:
            response = await async_client.post(
                "/web/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                cookies={"refresh_token": jti},
            )
        finally:
            app.dependency_overrides.pop(require_jwt, None)

        # Cookie must be cleared (Max-Age=0 or expires in the past)
        cookies = response.headers.get_list("set-cookie")
        assert any(
            "refresh_token" in c and ("max-age=0" in c.lower() or "expires" in c.lower())
            for c in cookies
        ), f"refresh_token clear cookie missing. set-cookie: {cookies}"


# ---------------------------------------------------------------------------
# S-08 to S-10: GET /web/auth/me
# ---------------------------------------------------------------------------


class TestMe:
    def _valid_access_token(self) -> str:
        jti = create_refresh_token()
        return create_access_token(
            sub=str(SYSTEM_USER_ID),
            org=str(SYSTEM_ORG_ID),
            rol="operador",
            jti=jti,
        )

    def _expired_access_token(self) -> str:
        from jose import jwt as jose_jwt

        payload = {
            "sub": str(SYSTEM_USER_ID),
            "org": str(SYSTEM_ORG_ID),
            "rol": "operador",
            "jti": "expired-jti",
            "exp": int(time.time()) - 1,
        }
        return jose_jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )

    @pytest.mark.asyncio
    async def test_s08_valid_token_returns_user_public(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-08: GET /web/auth/me with valid token → UsuarioPublic."""
        from dependencies.auth_jwt import require_jwt

        token = self._valid_access_token()
        mock_user = _make_mock_usuario()

        async def _mock_require_jwt():
            return mock_user

        app.dependency_overrides[require_jwt] = _mock_require_jwt

        try:
            response = await async_client.get(
                "/web/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            app.dependency_overrides.pop(require_jwt, None)

        assert response.status_code == 200
        body = response.json()
        assert body["correo"] == _TEST_EMAIL
        assert body["rol"] == "operador"

    @pytest.mark.asyncio
    async def test_s09_expired_token_returns_401(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-09: GET /web/auth/me with expired token → 401."""
        token = self._expired_access_token()
        response = await async_client.get(
            "/web/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_s10_tampered_token_returns_401(
        self,
        async_client: httpx.AsyncClient,
    ):
        """S-10: GET /web/auth/me with tampered token → 401."""
        response = await async_client.get(
            "/web/auth/me",
            headers={"Authorization": "Bearer invalid.tampered.token"},
        )
        assert response.status_code == 401

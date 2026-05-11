"""Unit tests for auth_jwt dependency — require_jwt behavior.

Tests run WITHOUT real DB (unit-level mocking via dependency_overrides).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import get_session
from services.jwt_service import create_access_token, create_refresh_token


def _make_test_app() -> FastAPI:
    """Return a minimal FastAPI app with require_jwt on a probe endpoint."""
    from dependencies.auth_jwt import require_jwt
    from fastapi import Depends
    from fastapi import FastAPI as FA

    probe = FA()

    @probe.get("/probe")
    async def _probe(usuario=Depends(require_jwt)):
        return {"id": str(usuario.id_usuario)}

    return probe


class TestRequireJwt:
    """Tests for require_jwt FastAPI dependency."""

    def _make_token(self, user_id: str = "user-1", org: str = "org-1") -> str:
        jti = create_refresh_token()
        return create_access_token(sub=user_id, org=org, rol="operador", jti=jti)

    def test_valid_token_returns_usuario(self):
        """Valid Bearer token → dependency returns Usuario from DB."""
        from dependencies.auth_jwt import require_jwt

        app = _make_test_app()
        mock_user = MagicMock()
        mock_user.id_usuario = uuid.UUID("019e0d75-323e-74b3-a249-909b3f77ee9f")
        mock_user.deleted_at = None

        # Override both session and require_jwt
        async def _mock_session():
            yield MagicMock()

        app.dependency_overrides[get_session] = _mock_session
        app.dependency_overrides[require_jwt] = lambda: mock_user

        with TestClient(app) as c:
            response = c.get("/probe")
        assert response.status_code == 200
        assert "019e0d75" in response.json()["id"]

    def test_missing_token_raises_401(self):
        """Missing Authorization header → 401."""
        from dependencies.auth_jwt import require_jwt

        app = _make_test_app()

        async def _mock_session():
            yield MagicMock()

        app.dependency_overrides[get_session] = _mock_session

        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.get("/probe")
        assert response.status_code == 401

    def test_tampered_token_raises_401(self):
        """Tampered Bearer token → 401."""
        from dependencies.auth_jwt import require_jwt

        app = _make_test_app()

        async def _mock_session():
            yield MagicMock()

        app.dependency_overrides[get_session] = _mock_session

        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.get("/probe", headers={"Authorization": "Bearer invalid.token.here"})
        assert response.status_code == 401

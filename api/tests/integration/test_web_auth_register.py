"""Tests para POST /web/auth/register (R-75).

Estrategia:
- TestClient con FastAPI minimal app + override de get_session
- DB mockeada: controla si el email ya existe o no
- No necesita Redis ni JWT

Spec coverage (R-75):
  - POST /register con datos validos → 201, {id_usuario, correo, nombre, rol, plan}
  - POST /register sin JWT en respuesta (NO debe haber token)
  - POST /register con email duplicado → 409 Conflict
  - POST /register con password < 8 chars → 422 Unprocessable
  - POST /register con email invalido → 422 Unprocessable
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_session
from models.usuario import Usuario
from routers.web_auth import router as web_auth_router

# ---------------------------------------------------------------------------
# Minimal test app
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(web_auth_router)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_allowing_register(
    *, existing_user: Usuario | None = None
) -> type:
    """Mock de session: get_user_by_email devuelve existing_user (o None)."""

    class _FakeScalars:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalars(self):
            return _FakeScalars(self._value)

    inserted_user: list[Usuario] = []

    class _FakeSession:
        async def execute(self, _stmt):
            return _FakeResult(existing_user)

        def add(self, obj):
            if isinstance(obj, Usuario):
                # Assign a fake UUID so the response can serialize
                if not hasattr(obj, "id_usuario") or obj.id_usuario is None:
                    obj.id_usuario = uuid.uuid4()
                inserted_user.append(obj)

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def refresh(self, obj):
            pass

    async def _override() -> AsyncGenerator[_FakeSession, None]:
        yield _FakeSession()

    return _override


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def register_client():
    """TestClient limpio, dependency overrides reseteados entre tests."""
    with TestClient(_test_app) as c:
        yield c
    _test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — R-75: registro exitoso
# ---------------------------------------------------------------------------


def test_register_success_returns_201(register_client):
    """POST /register con datos validos → 201 y body con campos correctos (R-75)."""
    _test_app.dependency_overrides[get_session] = _session_allowing_register(
        existing_user=None
    )

    response = register_client.post(
        "/web/auth/register",
        json={
            "correo": "nuevo@example.com",
            "nombre": "Test User",
            "contrasena": "securepassword123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["correo"] == "nuevo@example.com"
    assert body["nombre"] == "Test User"
    assert body["rol"] == "admin"  # first user of an org is always admin (R-75)
    assert body["plan"] == "basic"
    assert "id_usuario" in body


def test_register_response_has_no_token(register_client):
    """POST /register no debe incluir access_token en la respuesta (R-75)."""
    _test_app.dependency_overrides[get_session] = _session_allowing_register(
        existing_user=None
    )

    response = register_client.post(
        "/web/auth/register",
        json={
            "correo": "notoken@example.com",
            "nombre": "No Token User",
            "contrasena": "validpass456",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert "access_token" not in body
    assert "token" not in body


# ---------------------------------------------------------------------------
# Tests — R-75: email duplicado → 409
# ---------------------------------------------------------------------------


def test_register_duplicate_email_returns_409(register_client):
    """POST /register con email ya existente → 409 Conflict (R-75)."""
    existing = MagicMock(spec=Usuario)
    existing.correo = "existente@example.com"

    _test_app.dependency_overrides[get_session] = _session_allowing_register(
        existing_user=existing
    )

    response = register_client.post(
        "/web/auth/register",
        json={
            "correo": "existente@example.com",
            "nombre": "Otro User",
            "contrasena": "validpass789",
        },
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Tests — R-75: validacion de campos → 422
# ---------------------------------------------------------------------------


def test_register_short_password_returns_422(register_client):
    """POST /register con contrasena < 8 chars → 422 Unprocessable (R-75)."""
    _test_app.dependency_overrides[get_session] = _session_allowing_register()

    response = register_client.post(
        "/web/auth/register",
        json={
            "correo": "user@example.com",
            "nombre": "Short Pass",
            "contrasena": "short",  # 5 chars — below minimum
        },
    )

    assert response.status_code == 422


def test_register_invalid_email_returns_422(register_client):
    """POST /register con email invalido → 422 Unprocessable (R-75)."""
    _test_app.dependency_overrides[get_session] = _session_allowing_register()

    response = register_client.post(
        "/web/auth/register",
        json={
            "correo": "not-a-valid-email",
            "nombre": "Bad Email",
            "contrasena": "validpass123",
        },
    )

    assert response.status_code == 422

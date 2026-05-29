"""Tests para POST/DELETE/GET /web/auth/api-key (R-76, R-77, R-78).

Estrategia:
- TestClient con app minimal + override de require_jwt y get_session
- El mock de usuario es un MagicMock con atributos mutables reales
  (para que el endpoint pueda asignar token_api_prefix y token_api_hash)

Spec coverage:
  R-76: POST /api-key → 201, plaintext key en body, prefix y hash guardados
  R-76: POST /api-key segunda vez → sobreescribe key anterior (overwrite)
  R-77: DELETE /api-key → 200, prefix y hash seteados a None
  R-78: GET /api-key/status sin key → {has_key: false, prefix: null}
  R-78: GET /api-key/status con key → {has_key: true, prefix: "xxxx..."}
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_session
from dependencies.auth_jwt import require_jwt
from routers.web_auth import router as web_auth_router

# ---------------------------------------------------------------------------
# Minimal test app
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(web_auth_router)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MutableUsuario:
    """Usuario con atributos mutables para que el endpoint pueda asignarlos."""

    def __init__(self, *, token_api_prefix=None, token_api_hash=None):
        self.id_usuario = uuid.uuid4()
        self.token_api_prefix = token_api_prefix
        self.token_api_hash = token_api_hash


def _make_session_for_apikey() -> type:
    """Mock session que soporta commit sin DB real."""

    class _FakeSession:
        async def commit(self):
            pass

    async def _override() -> AsyncGenerator[_FakeSession, None]:
        yield _FakeSession()

    return _override


def _jwt_override(usuario):
    """Factory: override require_jwt para retornar usuario especifico."""
    def _override():
        return usuario
    return _override


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def apikey_client():
    """TestClient limpio, dependency overrides reseteados entre tests."""
    with TestClient(_test_app) as c:
        yield c
    _test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# R-76: POST /api-key — generar key
# ---------------------------------------------------------------------------


def test_generate_api_key_returns_201_with_plaintext(apikey_client):
    """POST /api-key → 201 con api_key plaintext en body (R-76)."""
    usuario = _MutableUsuario()
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)
    _test_app.dependency_overrides[get_session] = _make_session_for_apikey()

    response = apikey_client.post("/web/auth/api-key")

    assert response.status_code == 201
    body = response.json()
    assert "api_key" in body
    assert isinstance(body["api_key"], str)
    assert len(body["api_key"]) > 0
    assert "message" in body


def test_generate_api_key_stores_prefix_and_hash(apikey_client):
    """POST /api-key → guarda prefix[:8] y bcrypt hash en usuario (R-76)."""
    usuario = _MutableUsuario()
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)
    _test_app.dependency_overrides[get_session] = _make_session_for_apikey()

    response = apikey_client.post("/web/auth/api-key")
    plain_key = response.json()["api_key"]

    # prefix must be the first 8 chars of the plain key
    assert usuario.token_api_prefix == plain_key[:8]
    # hash must verify against the plain key
    assert usuario.token_api_hash is not None
    assert bcrypt.checkpw(plain_key.encode(), usuario.token_api_hash.encode())


def test_generate_api_key_twice_overwrites_previous(apikey_client):
    """POST /api-key segunda vez → sobreescribe el prefix y hash anteriores (R-76)."""
    usuario = _MutableUsuario(
        token_api_prefix="oldprefi",
        token_api_hash="$2b$04$oldhash",
    )
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)
    _test_app.dependency_overrides[get_session] = _make_session_for_apikey()

    response = apikey_client.post("/web/auth/api-key")
    new_plain_key = response.json()["api_key"]

    assert response.status_code == 201
    assert usuario.token_api_prefix != "oldprefi"
    assert usuario.token_api_prefix == new_plain_key[:8]


# ---------------------------------------------------------------------------
# R-77: DELETE /api-key — revocar key
# ---------------------------------------------------------------------------


def test_revoke_api_key_returns_200(apikey_client):
    """DELETE /api-key → 200 con message (R-77)."""
    usuario = _MutableUsuario(
        token_api_prefix="ab12cd34",
        token_api_hash="$2b$04$somehash",
    )
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)
    _test_app.dependency_overrides[get_session] = _make_session_for_apikey()

    response = apikey_client.delete("/web/auth/api-key")

    assert response.status_code == 200
    assert "message" in response.json()


def test_revoke_api_key_nullifies_prefix_and_hash(apikey_client):
    """DELETE /api-key → prefix y hash quedan en None (R-77)."""
    usuario = _MutableUsuario(
        token_api_prefix="ab12cd34",
        token_api_hash="$2b$04$somehash",
    )
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)
    _test_app.dependency_overrides[get_session] = _make_session_for_apikey()

    apikey_client.delete("/web/auth/api-key")

    assert usuario.token_api_prefix is None
    assert usuario.token_api_hash is None


# ---------------------------------------------------------------------------
# R-78: GET /api-key/status
# ---------------------------------------------------------------------------


def test_api_key_status_without_key_returns_has_key_false(apikey_client):
    """GET /api-key/status sin key → {has_key: false, prefix: null} (R-78)."""
    usuario = _MutableUsuario()  # no key
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)

    response = apikey_client.get("/web/auth/api-key/status")

    assert response.status_code == 200
    body = response.json()
    assert body["has_key"] is False
    assert body["prefix"] is None


def test_api_key_status_with_key_returns_has_key_true_and_prefix(apikey_client):
    """GET /api-key/status con key activa → {has_key: true, prefix: 'ab12cd34'} (R-78)."""
    usuario = _MutableUsuario(
        token_api_prefix="ab12cd34",
        token_api_hash="$2b$04$somehash",
    )
    _test_app.dependency_overrides[require_jwt] = _jwt_override(usuario)

    response = apikey_client.get("/web/auth/api-key/status")

    assert response.status_code == 200
    body = response.json()
    assert body["has_key"] is True
    assert body["prefix"] == "ab12cd34"

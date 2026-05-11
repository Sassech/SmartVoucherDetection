"""Tests for the `require_api_key` FastAPI dependency (A3 — R-14 through R-16).

Strategy:
- Test the dependency logic in isolation via a minimal FastAPI test app,
  overriding the `get_session` dependency with a mock session that controls
  the DB result set.
- bcrypt hashes are generated ONCE at module level (cost=4 for speed in tests).
- Covers all spec scenarios: valid key, missing key, wrong key, no users,
  deleted user ignored.

Spec coverage:
  R-14: Valid key returns Usuario ORM object
  R-15: Missing / empty key raises 401 "API key required"
  R-16: Wrong key raises 401 "Invalid API key" (timing-safe, same message)
  R-17: Protected endpoints reject missing key; /health remains public
  R-18: Regression gate (existing tests continue passing with override)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import bcrypt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from database import get_session
from models.usuario import Usuario

# ---------------------------------------------------------------------------
# Module-level constants — bcrypt with cost=4 keeps tests fast.
# ---------------------------------------------------------------------------

_PLAIN_KEY = "test-valid-api-key-abc123"
_VALID_HASH = bcrypt.hashpw(_PLAIN_KEY.encode(), bcrypt.gensalt(rounds=4)).decode()

_OTHER_PLAIN_KEY = "other-valid-key-xyz789"
_OTHER_HASH = bcrypt.hashpw(_OTHER_PLAIN_KEY.encode(), bcrypt.gensalt(rounds=4)).decode()

_WRONG_KEY = "this-is-not-the-right-key"


# ---------------------------------------------------------------------------
# Helpers to build mock sessions
# ---------------------------------------------------------------------------


def _make_usuario(*, token_api_hash: str | None = _VALID_HASH, deleted_at=None) -> Usuario:
    """Return a minimal Usuario ORM instance for testing."""
    user = MagicMock(spec=Usuario)
    user.id_usuario = "mock-uuid-0001"
    user.token_api_hash = token_api_hash
    user.deleted_at = deleted_at
    return user


def _session_with_users(users: list) -> type:
    """Return an async generator override for get_session yielding a fake session."""

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    class _FakeSession:
        async def execute(self, _stmt):
            return _FakeResult(users)

    async def _override() -> AsyncGenerator[_FakeSession, None]:
        yield _FakeSession()

    return _override


# ---------------------------------------------------------------------------
# Minimal test app that exercises require_api_key directly
# ---------------------------------------------------------------------------

# Import AFTER writing the file (this will fail in RED phase — expected)
from dependencies.auth_api_key import require_api_key  # noqa: E402

_test_app = FastAPI()


@_test_app.get("/protected")
async def _protected_endpoint(user: Usuario = Depends(require_api_key)) -> dict:
    return {"id_usuario": str(user.id_usuario)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client():
    """TestClient wired to the minimal test app with cleanup."""
    with TestClient(_test_app) as c:
        yield c
    _test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — R-15: Missing / empty key → 401 "API key required"
# ---------------------------------------------------------------------------


def test_missing_key_returns_401(auth_client):
    """No X-API-Key header → 401 with 'API key required' detail (R-15)."""
    # Provide users in DB so we know the 401 is from missing header, not empty DB.
    _test_app.dependency_overrides[get_session] = _session_with_users(
        [_make_usuario()]
    )

    response = auth_client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "API key required"


def test_empty_key_returns_401(auth_client):
    """X-API-Key: '' (empty string) → 401 'API key required' (R-15)."""
    _test_app.dependency_overrides[get_session] = _session_with_users(
        [_make_usuario()]
    )

    response = auth_client.get("/protected", headers={"X-API-Key": ""})

    assert response.status_code == 401
    assert response.json()["detail"] == "API key required"


# ---------------------------------------------------------------------------
# Tests — R-16: Wrong key → 401 "Invalid API key" (timing-safe)
# ---------------------------------------------------------------------------


def test_invalid_key_returns_401(auth_client):
    """Wrong key with users present → 401 'Invalid API key' (R-16)."""
    _test_app.dependency_overrides[get_session] = _session_with_users(
        [_make_usuario(token_api_hash=_VALID_HASH)]
    )

    response = auth_client.get("/protected", headers={"X-API-Key": _WRONG_KEY})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_no_users_with_hash_returns_401(auth_client):
    """No users with token_api_hash → 401 'Invalid API key' (R-16)."""
    _test_app.dependency_overrides[get_session] = _session_with_users([])

    response = auth_client.get("/protected", headers={"X-API-Key": _PLAIN_KEY})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_user_with_null_hash_not_matched(auth_client):
    """User with token_api_hash=None is skipped (R-16)."""
    _test_app.dependency_overrides[get_session] = _session_with_users(
        [_make_usuario(token_api_hash=None)]
    )

    response = auth_client.get("/protected", headers={"X-API-Key": _PLAIN_KEY})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


# ---------------------------------------------------------------------------
# Tests — R-14: Valid key returns Usuario
# ---------------------------------------------------------------------------


def test_valid_key_returns_usuario(auth_client):
    """Valid key matching bcrypt hash → 200 and returns id_usuario (R-14)."""
    user = _make_usuario(token_api_hash=_VALID_HASH)
    _test_app.dependency_overrides[get_session] = _session_with_users([user])

    response = auth_client.get("/protected", headers={"X-API-Key": _PLAIN_KEY})

    assert response.status_code == 200
    assert response.json()["id_usuario"] == str(user.id_usuario)


def test_valid_key_matches_correct_user_among_many(auth_client):
    """Valid key finds the right user even when multiple users are present (R-14)."""
    user_a = _make_usuario(token_api_hash=_VALID_HASH)
    user_a.id_usuario = "uuid-aaa"
    user_b = _make_usuario(token_api_hash=_OTHER_HASH)
    user_b.id_usuario = "uuid-bbb"

    _test_app.dependency_overrides[get_session] = _session_with_users([user_a, user_b])

    response = auth_client.get("/protected", headers={"X-API-Key": _OTHER_PLAIN_KEY})

    assert response.status_code == 200
    assert response.json()["id_usuario"] == "uuid-bbb"


# ---------------------------------------------------------------------------
# Tests — R-14: Deleted users are ignored
# ---------------------------------------------------------------------------


def test_deleted_user_ignored(auth_client):
    """Deleted user (deleted_at != None) is filtered at DB query level.

    The mock session is built to return NO users (simulating the query
    WHERE deleted_at IS NULL filtering them out) — proving the dependency
    returns 401 when only deleted users exist.
    """
    # The dependency queries WHERE deleted_at IS NULL — we simulate the DB
    # returning an empty result (deleted users filtered by query).
    _test_app.dependency_overrides[get_session] = _session_with_users([])

    response = auth_client.get("/protected", headers={"X-API-Key": _PLAIN_KEY})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


# ---------------------------------------------------------------------------
# Tests — R-17: Protected endpoints enforce auth; /health is public
# ---------------------------------------------------------------------------


def test_health_endpoint_is_public_no_key_needed():
    """GET /health does not require X-API-Key header (R-17)."""
    from main import app as main_app

    with TestClient(main_app) as c:
        response = c.get("/health")

    # /health always returns 200 regardless of service state
    assert response.status_code == 200


def test_upload_slip_without_key_returns_401():
    """POST /upload-slip without X-API-Key → 401 (R-17, proves auth is active).

    This test does NOT override require_api_key — it intentionally lets
    require_api_key run without a key to prove authentication is enforced.
    The session override returns an empty user list so auth fails cleanly
    before any upload logic executes.
    """
    from main import app as main_app

    # Provide a session that returns no users for require_api_key query
    # AND handles any other DB query (returning empty result with all methods).
    async def _no_users_session() -> AsyncGenerator:
        class _EmptyScalars:
            def all(self):
                return []

            def scalar_one_or_none(self):
                return None

            def scalar_one(self):
                return 0

        class _EmptyResult:
            def scalars(self):
                return _EmptyScalars()

            def scalar_one_or_none(self):
                return None

            def scalar_one(self):
                return 0

        class _EmptySession:
            async def execute(self, _stmt):
                return _EmptyResult()

        yield _EmptySession()

    main_app.dependency_overrides[get_session] = _no_users_session
    try:
        with TestClient(main_app) as c:
            import io

            from PIL import Image

            buf = io.BytesIO()
            Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
            buf.seek(0)
            response = c.post(
                "/upload-slip",
                files={"file": ("test.png", buf, "image/png")},
            )
        assert response.status_code == 401
    finally:
        main_app.dependency_overrides.pop(get_session, None)

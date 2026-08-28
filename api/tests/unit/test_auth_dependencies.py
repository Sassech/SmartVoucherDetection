"""TDD coverage for auth_any.py, auth_jwt.py, auth_api_key.py — branch 80%.

Uses direct dependency calls with mocked AsyncSession / redis / jwt.
Bcrypt hashes use rounds=4 for speed (DUMMY_BCRYPT_ROUNDS=4).

`verify_token` is patched at `services.auth_helpers.verify_token` (not
`dependencies.auth_jwt`/`dependencies.auth_any`) because sonarqube-final-hardening
AD-02 moved the shared credential-verification logic into
`services/auth_helpers.py`; the dependencies modules now delegate to it.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Helpers: bcrypt hashes with cost=4
# ---------------------------------------------------------------------------

_PLAIN = "test-api-key-12345"
_HASH = bcrypt.hashpw(_PLAIN.encode(), bcrypt.gensalt(rounds=4)).decode()
_PREFIX = _PLAIN[:8]

_OTHER_PLAIN = "other-key-99999"
_OTHER_HASH = bcrypt.hashpw(_OTHER_PLAIN.encode(), bcrypt.gensalt(rounds=4)).decode()

_WRONG = "wrong-key-00000"


def _make_user(*, token_hash=_HASH, deleted_at=None, id_usuario=None):
    u = MagicMock()
    u.id_usuario = id_usuario or uuid.uuid4()
    u.token_api_hash = token_hash
    u.deleted_at = deleted_at
    u.id_organizacion = uuid.uuid4()
    u.correo = "test@example.com"
    u.rol = "operador"
    return u


def _mock_session_with_users(users: list) -> AsyncMock:
    mock = AsyncMock()
    res = MagicMock()
    res.scalars.return_value.all.return_value = users
    res.scalar_one_or_none.return_value = users[0] if users else None
    # For auth_jwt / auth_bearer that use scalar_one_or_none, return first user or None
    # For api_key that uses scalars().all(), return list
    mock.execute.return_value = res
    return mock


def _session_scalar_one_or_none(user_or_none) -> AsyncMock:
    mock = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = user_or_none
    mock.execute.return_value = res
    return mock


def _session_scalars_all(users: list) -> AsyncMock:
    mock = AsyncMock()
    res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = users
    res.scalars.return_value = scalars
    mock.execute.return_value = res
    return mock


# ---------------------------------------------------------------------------
# require_api_key tests (auth_api_key.py)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_api_key_missing_raises_401():
    from dependencies.auth_api_key import require_api_key

    db = _mock_session_with_users([])
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key="", db=db)
    assert exc.value.status_code == 401
    assert "API key required" in exc.value.detail


@pytest.mark.asyncio
async def test_require_api_key_invalid_raises_401():
    from dependencies.auth_api_key import require_api_key

    db = _session_scalars_all([])
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key="invalid-key-xyz", db=db)
    assert exc.value.status_code == 401
    assert "Invalid API key" in exc.value.detail


@pytest.mark.asyncio
async def test_require_api_key_valid_returns_user():
    from dependencies.auth_api_key import require_api_key

    user = _make_user(token_hash=_HASH)
    db = _session_scalars_all([user])
    result = await require_api_key(x_api_key=_PLAIN, db=db)
    assert result is user


@pytest.mark.asyncio
async def test_require_api_key_wrong_key_among_candidates_401():
    from dependencies.auth_api_key import require_api_key

    user = _make_user(token_hash=_HASH)
    db = _session_scalars_all([user])
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key=_WRONG, db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_null_hash_not_matched():
    from dependencies.auth_api_key import require_api_key

    user = _make_user(token_hash=None)
    db = _session_scalars_all([user])
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key=_PLAIN, db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_api_key_correct_user_among_many():
    from dependencies.auth_api_key import require_api_key

    u1 = _make_user(token_hash=_OTHER_HASH)
    u2 = _make_user(token_hash=_HASH)
    db = _session_scalars_all([u1, u2])
    result = await require_api_key(x_api_key=_PLAIN, db=db)
    assert result is u2


# ---------------------------------------------------------------------------
# auth_jwt require_jwt tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_jwt_none_token_401():
    from dependencies.auth_jwt import require_jwt

    db = _session_scalar_one_or_none(None)
    with pytest.raises(HTTPException) as exc:
        await require_jwt(token=None, db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_jwt_invalid_token_propagates_401():
    from dependencies.auth_jwt import require_jwt

    db = _session_scalar_one_or_none(None)
    # verify_token raises HTTPException 401 for invalid token
    with patch(
        "services.auth_helpers.verify_token",
        side_effect=HTTPException(status_code=401, detail="Invalid token"),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_jwt(token="bad.token", db=db)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_jwt_missing_sub_401():
    from dependencies.auth_jwt import require_jwt

    db = _session_scalar_one_or_none(None)
    with patch("services.auth_helpers.verify_token", return_value={}):
        with pytest.raises(HTTPException) as exc:
            await require_jwt(token="t", db=db)
        assert exc.value.status_code == 401
        assert "Invalid token payload" in exc.value.detail


@pytest.mark.asyncio
async def test_require_jwt_invalid_uuid_sub_401():
    from dependencies.auth_jwt import require_jwt

    db = _session_scalar_one_or_none(None)
    with patch(
        "services.auth_helpers.verify_token", return_value={"sub": "not-a-uuid"}
    ):
        with pytest.raises(HTTPException) as exc:
            await require_jwt(token="t", db=db)
        assert exc.value.status_code == 401
        assert "Invalid token subject" in exc.value.detail


@pytest.mark.asyncio
async def test_require_jwt_user_not_found_401():
    from dependencies.auth_jwt import require_jwt

    uid = str(uuid.uuid4())
    db = _session_scalar_one_or_none(None)
    with patch("services.auth_helpers.verify_token", return_value={"sub": uid}):
        with pytest.raises(HTTPException) as exc:
            await require_jwt(token="t", db=db)
        assert exc.value.status_code == 401
        assert "User not found" in exc.value.detail


@pytest.mark.asyncio
async def test_require_jwt_valid_returns_user():
    from dependencies.auth_jwt import require_jwt

    uid = uuid.uuid4()
    user = _make_user(id_usuario=uid)
    db = _session_scalar_one_or_none(user)
    with patch("services.auth_helpers.verify_token", return_value={"sub": str(uid)}):
        result = await require_jwt(token="t", db=db)
        assert result is user


# ---------------------------------------------------------------------------
# auth_any: _authenticate_api_key, _authenticate_bearer, require_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_any_api_key_valid():
    from dependencies.auth_any import _authenticate_api_key

    user = _make_user(token_hash=_HASH)
    db = _session_scalars_all([user])
    result = await _authenticate_api_key(_PLAIN, db)
    assert result is user


@pytest.mark.asyncio
async def test_auth_any_api_key_invalid():
    from dependencies.auth_any import _authenticate_api_key

    user = _make_user(token_hash=_HASH)
    db = _session_scalars_all([user])
    with pytest.raises(HTTPException) as exc:
        await _authenticate_api_key(_WRONG, db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_any_bearer_valid():
    from dependencies.auth_any import _authenticate_bearer

    uid = uuid.uuid4()
    user = _make_user(id_usuario=uid)
    db = _session_scalar_one_or_none(user)
    with patch("services.auth_helpers.verify_token", return_value={"sub": str(uid)}):
        result = await _authenticate_bearer("Bearer tkn", db)
        # need proper token format: "Bearer " prefix stripped inside function
        # our patch must handle stripping
    # redo with correct header
    with patch("services.auth_helpers.verify_token", return_value={"sub": str(uid)}):
        result = await _authenticate_bearer("Bearer abc123", db)
        assert result is user


@pytest.mark.asyncio
async def test_auth_any_bearer_invalid_token_propagates():
    from dependencies.auth_any import _authenticate_bearer

    db = _session_scalar_one_or_none(None)
    with patch(
        "services.auth_helpers.verify_token",
        side_effect=HTTPException(status_code=401, detail="Invalid token"),
    ):
        with pytest.raises(HTTPException) as exc:
            await _authenticate_bearer("Bearer bad", db)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_any_bearer_generic_exception_becomes_401():
    from dependencies.auth_any import _authenticate_bearer

    db = _session_scalar_one_or_none(None)
    with patch("services.auth_helpers.verify_token", side_effect=ValueError("boom")):
        with pytest.raises(HTTPException) as exc:
            await _authenticate_bearer("Bearer bad", db)
        assert exc.value.status_code == 401
        assert "Invalid token" in exc.value.detail


@pytest.mark.asyncio
async def test_auth_any_bearer_missing_sub():
    from dependencies.auth_any import _authenticate_bearer

    db = _session_scalar_one_or_none(None)
    with patch("services.auth_helpers.verify_token", return_value={}):
        with pytest.raises(HTTPException) as exc:
            await _authenticate_bearer("Bearer t", db)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_any_bearer_invalid_uuid_sub():
    from dependencies.auth_any import _authenticate_bearer

    db = _session_scalar_one_or_none(None)
    with patch("services.auth_helpers.verify_token", return_value={"sub": "not-uuid"}):
        with pytest.raises(HTTPException) as exc:
            await _authenticate_bearer("Bearer t", db)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_any_bearer_user_not_found():
    from dependencies.auth_any import _authenticate_bearer

    uid = str(uuid.uuid4())
    db = _session_scalar_one_or_none(None)
    with patch("services.auth_helpers.verify_token", return_value={"sub": uid}):
        with pytest.raises(HTTPException) as exc:
            await _authenticate_bearer("Bearer t", db)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_prefers_api_key_over_bearer():
    from dependencies.auth_any import require_user

    user_api = _make_user(id_usuario=uuid.uuid4(), token_hash=_HASH)
    db = _session_scalars_all([user_api])
    req = MagicMock()
    req.headers.get.return_value = "Bearer should_not_be_used"
    result = await require_user(request=req, x_api_key=_PLAIN, db=db)
    assert result is user_api


@pytest.mark.asyncio
async def test_require_user_bearer_when_no_api_key():
    from dependencies.auth_any import require_user

    uid = uuid.uuid4()
    user = _make_user(id_usuario=uid)
    db = _session_scalar_one_or_none(user)
    req = MagicMock()
    req.headers.get.return_value = "Bearer abc"
    with patch("services.auth_helpers.verify_token", return_value={"sub": str(uid)}):
        result = await require_user(request=req, x_api_key="", db=db)
        assert result is user


@pytest.mark.asyncio
async def test_require_user_neither_returns_401():
    from dependencies.auth_any import require_user

    db = _session_scalars_all([])
    req = MagicMock()
    req.headers.get.return_value = ""
    with pytest.raises(HTTPException) as exc:
        await require_user(request=req, x_api_key="", db=db)
    assert exc.value.status_code == 401
    assert "Authentication required" in exc.value.detail


@pytest.mark.asyncio
async def test_require_user_bearer_header_missing_prefix_401():
    from dependencies.auth_any import require_user

    db = _session_scalars_all([])
    req = MagicMock()
    req.headers.get.return_value = "Basic abc"
    with pytest.raises(HTTPException) as exc:
        await require_user(request=req, x_api_key="", db=db)
    assert exc.value.status_code == 401

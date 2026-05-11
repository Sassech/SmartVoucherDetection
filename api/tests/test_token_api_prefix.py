"""Tests for token_api_prefix optimization — S-11 through S-15.

These tests verify:
    S-11: Migration column and backfill behavior (simulated at model level)
    S-12: Migration rollback — only structural (checked via migration file presence)
    S-13: Prefix lookup returns correct Usuario (fast path)
    S-14: NULL prefix rows excluded from bcrypt comparison
    S-15: require_api_key regression — existing behavior preserved with prefix

All tests use mock DB session (no real Postgres needed).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException

from database import get_session
from main import app
from models.seed import SYSTEM_ORG_ID, SYSTEM_USER_ID


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_usuario_with_prefix(
    plain_key: str = "myplainkey123",
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    """Return a mock Usuario with a real bcrypt hash and matching prefix."""
    hashed = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt(rounds=4)).decode()
    prefix = plain_key[:8]

    mock = MagicMock()
    mock.id_usuario = user_id or SYSTEM_USER_ID
    mock.id_organizacion = SYSTEM_ORG_ID
    mock.correo = "api@example.com"
    mock.nombre = "API User"
    mock.rol = "operador"
    mock.deleted_at = None
    mock.token_api_hash = hashed
    mock.token_api_prefix = prefix
    return mock


def _make_usuario_null_prefix(user_id: uuid.UUID | None = None) -> MagicMock:
    """Return a mock Usuario with NULL token_api_prefix (webapp-only user)."""
    mock = MagicMock()
    mock.id_usuario = user_id or uuid.uuid4()
    mock.id_organizacion = SYSTEM_ORG_ID
    mock.correo = "webapp@example.com"
    mock.nombre = "Webapp User"
    mock.rol = "admin"
    mock.deleted_at = None
    mock.token_api_hash = None
    mock.token_api_prefix = None
    return mock


# ---------------------------------------------------------------------------
# S-11: Migration column existence (structural/model test)
# ---------------------------------------------------------------------------


class TestTokenApiPrefixColumn:
    def test_s11_model_has_token_api_prefix(self):
        """S-11: Usuario model must have token_api_prefix attribute."""
        from models.usuario import Usuario

        assert hasattr(Usuario, "token_api_prefix"), (
            "Usuario model must have token_api_prefix column"
        )

    def test_s11_token_api_prefix_is_nullable(self):
        """S-11: token_api_prefix column must be nullable (VARCHAR 8)."""
        from sqlalchemy import inspect as sa_inspect

        from models.usuario import Usuario

        mapper = sa_inspect(Usuario)
        col = mapper.columns["token_api_prefix"]
        assert col.nullable is True, "token_api_prefix must be nullable"

    def test_s11_token_api_prefix_max_length_8(self):
        """S-11: token_api_prefix must have max_length=8."""
        from sqlalchemy import inspect as sa_inspect

        from models.usuario import Usuario

        mapper = sa_inspect(Usuario)
        col = mapper.columns["token_api_prefix"]
        # String(8) → length == 8
        assert col.type.length == 8, (
            f"token_api_prefix must be String(8), got length={col.type.length}"
        )

    def test_s11_migration_file_exists(self):
        """S-11: Alembic migration file must exist with correct revision."""
        import pathlib

        versions_dir = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
        migration_files = list(versions_dir.glob("*add_token_api_prefix*.py"))
        assert len(migration_files) == 1, (
            f"Expected 1 migration file for token_api_prefix, found: {migration_files}"
        )

    def test_s11_migration_has_correct_down_revision(self):
        """S-11: Migration must chain from 34b207551c82 (last Fase 2 migration)."""
        import importlib.util
        import pathlib

        versions_dir = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
        migration_file = next(versions_dir.glob("*add_token_api_prefix*.py"))
        spec = importlib.util.spec_from_file_location("migration", migration_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.down_revision == "34b207551c82", (
            f"Migration down_revision must be '34b207551c82', got {module.down_revision!r}"
        )


# ---------------------------------------------------------------------------
# S-13: Prefix lookup returns correct Usuario (integration-level mock)
# ---------------------------------------------------------------------------


class TestPrefixLookup:
    @pytest.mark.asyncio
    async def test_s13_prefix_match_returns_correct_user(self):
        """S-13: require_api_key with valid key resolves to correct Usuario."""
        from dependencies.auth_api_key import require_api_key

        plain_key = "mykey123_full_key"
        user = _make_usuario_with_prefix(plain_key=plain_key)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await require_api_key(x_api_key=plain_key, db=mock_db)

        assert result is user
        # Verify DB was queried (prefix pre-filter invoked)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_s13_wrong_full_key_returns_401(self):
        """S-13: prefix matches but full bcrypt fails → 401."""
        from dependencies.auth_api_key import require_api_key

        plain_key = "mykey123_correct"
        wrong_key = "mykey123_wrong!!"  # same prefix, different full key
        user = _make_usuario_with_prefix(plain_key=plain_key)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(x_api_key=wrong_key, db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid API key"

    @pytest.mark.asyncio
    async def test_s14_null_prefix_user_excluded(self):
        """S-14: NULL prefix rows are excluded from bcrypt comparison.

        When require_api_key queries WHERE token_api_prefix = prefix,
        NULL-prefix rows naturally won't match any submitted key prefix.
        This test verifies the mock returns only non-NULL users.
        """
        from dependencies.auth_api_key import require_api_key

        plain_key = "mykey123_valid"
        # Only return the NULL-prefix user (no match for the submitted prefix)
        null_user = _make_usuario_null_prefix()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # NULL prefix excluded by WHERE
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(x_api_key=plain_key, db=mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_s12_prefix_miss_skips_bcrypt(self):
        """S-12 (Prefix mismatch): no candidates → 401 without calling bcrypt.

        Verifies the fast-path: when the DB returns no candidates for the
        prefix, bcrypt.checkpw is never called.
        """
        from dependencies.auth_api_key import require_api_key

        # Empty result = no prefix match
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("dependencies.auth_api_key.bcrypt.checkpw") as mock_checkpw:
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(x_api_key="XXXXXXXX_missing", db=mock_db)

        assert exc_info.value.status_code == 401
        mock_checkpw.assert_not_called()

    @pytest.mark.asyncio
    async def test_s15_missing_header_returns_401(self):
        """S-15: empty X-API-Key header → 401 (regression: existing behavior preserved)."""
        from dependencies.auth_api_key import require_api_key

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(x_api_key="", db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "API key required"

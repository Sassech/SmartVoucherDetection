"""Tests para la validacion de Settings en api/config.py (6.F.1).

Verifica:
- SECRET_KEY < 32 chars → ValueError en Settings()
- SECRET_KEY = 32 chars → OK
- SECRET_KEY = 31 chars → ValueError
- Default Settings() → OK (clave default tiene >= 32 chars)
- cors_origins field existe y tiene valor por defecto
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_settings_weak_secret_key_raises_value_error():
    """Settings con secret_key < 32 chars levanta ValueError/ValidationError."""
    from config import Settings

    with pytest.raises((ValueError, ValidationError)):
        Settings(
            secret_key="short",
            database_url="postgresql+asyncpg://u:p@localhost/db",
            redis_url="redis://localhost",
            llama_server_url="http://localhost:8080",
        )


def test_settings_secret_key_exactly_32_chars_passes():
    """Settings con secret_key de exactamente 32 chars es valido."""
    from config import Settings

    s = Settings(
        secret_key="a" * 32,
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost",
        llama_server_url="http://localhost:8080",
    )
    assert s.secret_key == "a" * 32


def test_settings_secret_key_31_chars_raises_value_error():
    """Settings con secret_key de 31 chars levanta ValueError/ValidationError."""
    from config import Settings

    with pytest.raises((ValueError, ValidationError)):
        Settings(
            secret_key="a" * 31,
            database_url="postgresql+asyncpg://u:p@localhost/db",
            redis_url="redis://localhost",
            llama_server_url="http://localhost:8080",
        )


def test_settings_secret_key_longer_than_32_chars_passes():
    """Settings con secret_key de mas de 32 chars es valido."""
    from config import Settings

    s = Settings(
        secret_key="a" * 64,
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost",
        llama_server_url="http://localhost:8080",
    )
    assert len(s.secret_key) == 64


def test_default_settings_secret_key_is_valid():
    """El Settings() creado con la clave default tiene >= 32 chars (no lanza error).

    Verifica que el default de secret_key en config.py tiene >= 32 caracteres.
    """
    from config import Settings

    # Si el default tiene >= 32 chars, Settings() no deberia fallar.
    # Usamos _env_file=None para ignorar el .env del proyecto y solo
    # testear el valor hardcoded de la clase.
    # Cargamos solo la clave default inspeccionando el campo.
    field = Settings.model_fields.get("secret_key")
    assert field is not None
    default_val = field.default
    # Si no hay default (campo requerido) esto falla — lo esperado es que
    # haya un default de >= 32 chars.
    assert default_val is not None, "secret_key debe tener un valor default"
    assert len(str(default_val)) >= 32, (
        f"El default de secret_key debe tener >= 32 chars, tiene {len(str(default_val))}"
    )


def test_settings_has_cors_origins_field():
    """Settings tiene el campo cors_origins con valor por defecto."""
    from config import Settings

    field = Settings.model_fields.get("cors_origins")
    assert field is not None, "Settings debe tener campo cors_origins"


def test_settings_cors_origins_default_is_localhost():
    """El default de cors_origins incluye localhost:3000."""
    from config import Settings

    s = Settings(
        secret_key="a" * 32,
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost",
        llama_server_url="http://localhost:8080",
    )
    assert isinstance(s.cors_origins, list)
    assert len(s.cors_origins) >= 1
    assert "http://localhost:3000" in s.cors_origins

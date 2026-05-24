"""Pydantic v2 schemas para autenticacion JWT (Fase 4) y multi-user (Fase 7).

- `LoginRequest`: payload de POST /web/auth/login.
- `TokenResponse`: respuesta con access_token (tambien enviado como cookie).
- `UsuarioPublic`: DTO publico del usuario autenticado para GET /web/auth/me.
- `RegisterRequest`: payload de POST /web/auth/register (R-75).
- `UsuarioWithPlan`: respuesta de register con campo plan (R-75).
- `ApiKeyResponse`: respuesta de POST /web/auth/api-key con plaintext (R-76).
- `ApiKeyStatus`: respuesta de GET /web/auth/api-key/status (R-78).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Payload del endpoint de login."""

    correo: EmailStr
    contrasena: str


class TokenResponse(BaseModel):
    """Respuesta del login/refresh con access_token.

    `expires_in` es 15 * 60 = 900 segundos — fixture de test verifica esto.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes in seconds


class UsuarioPublic(BaseModel):
    """DTO publico del usuario autenticado.

    `from_attributes=True` permite construir desde un ORM via model_validate.
    """

    model_config = ConfigDict(from_attributes=True)

    id_usuario: uuid.UUID
    correo: str
    nombre: str
    rol: str
    id_organizacion: uuid.UUID


# ---------------------------------------------------------------------------
# Fase 7 — Multi-user registration and API key schemas (R-75/R-76/R-77/R-78)
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Payload de POST /web/auth/register (R-75).

    contrasena requiere minimo 8 caracteres (validacion por Field min_length).
    correo es validado como EmailStr por Pydantic.
    """

    correo: EmailStr
    nombre: str
    contrasena: str = Field(min_length=8)


class UsuarioWithPlan(BaseModel):
    """Respuesta de POST /web/auth/register — incluye campo plan (R-75).

    No devuelve token JWT — el usuario debe hacer login por separado.
    """

    model_config = ConfigDict(from_attributes=True)

    id_usuario: uuid.UUID
    correo: str
    nombre: str
    rol: str
    plan: str


class ApiKeyResponse(BaseModel):
    """Respuesta de POST /web/auth/api-key con el plaintext una sola vez (R-76).

    api_key es el token en texto plano — solo se retorna en esta respuesta.
    """

    api_key: str  # plaintext — mostrado ONCE
    message: str


class ApiKeyStatus(BaseModel):
    """Respuesta de GET /web/auth/api-key/status (R-78).

    has_key indica si el usuario tiene una API key activa.
    prefix es los primeros 8 chars del token (visible para identificacion).
    """

    has_key: bool
    prefix: str | None

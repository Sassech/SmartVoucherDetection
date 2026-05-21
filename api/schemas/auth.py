"""Pydantic v2 schemas para autenticacion JWT (Fase 4).

- `LoginRequest`: payload de POST /web/auth/login.
- `TokenResponse`: respuesta con access_token (tambien enviado como cookie).
- `UsuarioPublic`: DTO publico del usuario autenticado para GET /web/auth/me.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


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

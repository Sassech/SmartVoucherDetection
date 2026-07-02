"""Tests for GET /web/comprobantes/{id}/image — Issue 3a.

Three scenarios:
  1. Authenticated user, comprobante in their org, file exists on disk → 200 with image content
  2. File path in DB but file doesn't exist on disk → 404
  3. Comprobante belongs to different org → 403

Filesystem is mocked (tmp_path / unittest.mock) so tests don't need real files on disk.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.comprobante import Comprobante
from models.organizacion import Organizacion
from models.seed import SYSTEM_USER_ID
from models.usuario import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_comprobante_with_path(id_usuario: uuid.UUID, imagen_path: str) -> Comprobante:
    """Create a Comprobante with a specific imagen_path for image endpoint tests."""
    return Comprobante(
        id_usuario=id_usuario,
        imagen_path=imagen_path,
        texto_extraido="Sample text",
        referencia="REF-IMG-001",
        monto=500.00,
        fecha_deposito=date(2026, 3, 1),
        numero_operacion="OP-IMG-001",
        banco="BCP",
        hash_documento=f"imgtest{uuid.uuid4().hex[:57]}",
        estado_actual="valido",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def comprobante_with_file(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[Comprobante, Path]:
    """Comprobante in SYSTEM_ORG, imagen_path points to a real temp file."""
    img_file = tmp_path / "test_receipt.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)  # minimal PNG header

    c = _make_comprobante_with_path(SYSTEM_USER_ID, str(img_file))
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)
    return c, img_file


@pytest_asyncio.fixture
async def comprobante_missing_file(
    db_session: AsyncSession, tmp_path: Path
) -> Comprobante:
    """Comprobante in SYSTEM_ORG, imagen_path points to a NON-EXISTENT file."""
    non_existent = tmp_path / "does_not_exist.png"
    # Intentionally NOT creating the file

    c = _make_comprobante_with_path(SYSTEM_USER_ID, str(non_existent))
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def foreign_comprobante_with_file(
    db_session: AsyncSession, tmp_path: Path
) -> Comprobante:
    """Comprobante belonging to a DIFFERENT org — for 403 test."""
    foreign_org = Organizacion(
        nombre="Image Foreign Org",
        plan_suscripcion="basico",
    )
    db_session.add(foreign_org)
    await db_session.flush()
    await db_session.refresh(foreign_org)

    import bcrypt
    foreign_user = Usuario(
        id_organizacion=foreign_org.id_organizacion,
        nombre="Image Foreign User",
        correo="imgforeign@test.com",
        contrasena_hash=bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode(),
        rol="operador",
    )
    db_session.add(foreign_user)
    await db_session.flush()
    await db_session.refresh(foreign_user)

    img_file = tmp_path / "foreign_receipt.jpg"
    img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 12)  # minimal JPEG header

    c = _make_comprobante_with_path(foreign_user.id_usuario, str(img_file))
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)
    return c


# ---------------------------------------------------------------------------
# Image endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_endpoint_returns_file(
    client_jwt: AsyncClient,
    comprobante_with_file: tuple[Comprobante, Path],
) -> None:
    """Authenticated user, comprobante in their org, file exists on disk → 200 with image."""
    comprobante, img_file = comprobante_with_file
    assert img_file.exists(), "Test setup: temp file must exist"

    resp = await client_jwt.get(
        f"/web/comprobantes/{comprobante.id_comprobante}/image"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    # Verify actual file content is returned (not empty, not an error body)
    assert len(resp.content) > 0
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_image_endpoint_404_no_file(
    client_jwt: AsyncClient,
    comprobante_missing_file: Comprobante,
) -> None:
    """File path stored in DB but file doesn't exist on disk → 404."""
    resp = await client_jwt.get(
        f"/web/comprobantes/{comprobante_missing_file.id_comprobante}/image"
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_image_endpoint_403_foreign_org(
    client_jwt: AsyncClient,
    foreign_comprobante_with_file: Comprobante,
) -> None:
    """Comprobante belongs to different org → 403 Access denied."""
    resp = await client_jwt.get(
        f"/web/comprobantes/{foreign_comprobante_with_file.id_comprobante}/image"
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Access denied"
